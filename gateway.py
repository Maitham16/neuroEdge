from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from queue import Queue, Empty
from threading import Event, Lock
from typing import Dict, Any, List, Optional
from .lif import LIFAggregator
from .inhibition import InhibitionState


@dataclass
class GatewayStats:
    fires: int = 0
    suppressed_total: int = 0


class Gateway:
    def __init__(
        self,
        inq: Queue,
        inhibition: InhibitionState,
        agg_leak: float,
        agg_theta: float,
        beta: float,
        t_inh_steps: int,
        tx_power_w: float,
        payload_bytes: int,
        collision_mode: str,
        retention_multiplier: float,
        min_retention_s: float,
        max_recent: int = 5000,
    ) -> None:
        self.inq = inq
        self.inhibition = inhibition
        self.aggregator = LIFAggregator(leak=agg_leak, theta=agg_theta)
        self.beta = float(beta)
        self.t_inh_steps = int(t_inh_steps)
        self.tx_power_w = float(tx_power_w)
        self.payload_bytes = int(payload_bytes)
        self.collision_mode = collision_mode
        self.retention_multiplier = float(retention_multiplier)
        self.min_retention_s = float(min_retention_s)
        self._recent_msgs: deque[Dict[str, Any]] = deque(maxlen=max_recent)
        self._lock = Lock()
        self._stop = Event()
        self.stats = GatewayStats()

    def stop(self) -> None:
        self._stop.set()

    def _lorawan_airtime(self, payload: int) -> float:
        sf = 7
        bw = 125000.0
        cr = 1
        preamble = 8
        de = 1 if sf >= 11 and bw == 125000.0 else 0
        tsym = (2.0 ** sf) / bw
        num = 8 * payload - 4 * sf + 28 + 16
        den = 4 * (sf - 2 * de)
        payload_symb = 8 + max(int(num / den) * (cr + 4), 0)
        t_pre = (preamble + 4.25) * tsym
        t_pay = payload_symb * tsym
        return t_pre + t_pay

    def _process_message(self, msg: Dict[str, Any]) -> None:
        now = time.time()
        airtime = self._lorawan_airtime(self.payload_bytes)
        energy = airtime * self.tx_power_w
        start_s = now
        end_s = now + airtime
        msg["airtime_s"] = airtime
        msg["energy_j"] = energy
        msg["start_s"] = start_s
        msg["end_s"] = end_s
        spike_flag = int(msg.get("spike", 0)) == 1
        if spike_flag:
            fired = self.aggregator.step(1.0)
            if fired:
                self.stats.fires += 1
                self.inhibition.activate(self.beta, self.t_inh_steps)
        st = msg.get("suppressed_total")
        if st is not None:
            try:
                st_int = int(st)
            except Exception:
                st_int = None
            if st_int is not None and st_int > self.stats.suppressed_total:
                self.stats.suppressed_total = st_int
        self._recent_msgs.append(msg)

    def loop_once(self, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        try:
            msg = self.inq.get(timeout=timeout)
        except Empty:
            return None
        with self._lock:
            self._process_message(msg)
        return msg

    def run(self, timeout: float = 0.5) -> None:
        while not self._stop.is_set():
            self.loop_once(timeout=timeout)

    def _compute_collisions(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        for d in data:
            d["collided"] = False
            d["pairwise_collisions"] = 0
        candidates = []
        for idx, d in enumerate(data):
            node = d.get("node")
            if node is None:
                continue
            try:
                node_int = int(node)
            except Exception:
                continue
            try:
                start_s = float(d.get("start_s"))
                end_s = float(d.get("end_s"))
            except Exception:
                continue
            if self.collision_mode == "spikes":
                is_spike = int(d.get("spike", 0)) == 1
                if not is_spike:
                    continue
            candidates.append(
                {
                    "idx": idx,
                    "node": node_int,
                    "start_s": start_s,
                    "end_s": end_s,
                }
            )
        candidates.sort(key=lambda x: x["start_s"])
        n = len(candidates)
        for i in range(n):
            ci = candidates[i]
            j = i + 1
            while j < n:
                cj = candidates[j]
                if cj["start_s"] >= ci["end_s"]:
                    break
                if cj["node"] != ci["node"]:
                    di = data[ci["idx"]]
                    dj = data[cj["idx"]]
                    di["collided"] = True
                    dj["collided"] = True
                    di["pairwise_collisions"] += 1
                    dj["pairwise_collisions"] += 1
                j += 1
        per_node_collisions: Dict[str, int] = {}
        per_node_pairwise: Dict[str, int] = {}
        total_collided_messages = 0
        sum_pairwise = 0
        for d in data:
            node = d.get("node")
            if node is None:
                continue
            node_str = str(node)
            if d.get("collided"):
                total_collided_messages += 1
                per_node_collisions[node_str] = per_node_collisions.get(node_str, 0) + 1
            pc = d.get("pairwise_collisions", 0)
            if isinstance(pc, (int, float)):
                val = int(pc)
            else:
                try:
                    val = int(pc)
                except Exception:
                    val = 0
            if val:
                per_node_pairwise[node_str] = per_node_pairwise.get(node_str, 0) + val
                sum_pairwise += val
        total_pairwise_overlaps = sum_pairwise // 2
        return {
            "per_node_collisions": per_node_collisions,
            "per_node_pairwise": per_node_pairwise,
            "total_collided_messages": total_collided_messages,
            "total_pairwise_overlaps": total_pairwise_overlaps,
        }

    def snapshot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            data = list(self._recent_msgs)
            timestamps = [d.get("ts") for d in data]
            nodes_values: Dict[str, Dict[str, float]] = {}
            for d in data:
                ts = d.get("ts")
                node = d.get("node")
                if ts is None or node is None:
                    continue
                key = str(node)
                nodes_values.setdefault(key, {})
                try:
                    nodes_values[key][ts] = float(d.get("value", 0.0))
                except Exception:
                    nodes_values[key][ts] = 0.0
            nodes = {}
            for node, series in nodes_values.items():
                nodes[node] = {"values": [series.get(ts) for ts in timestamps]}
            if data:
                now = time.time()
                window = 60.0
                count = 0
                for d in data:
                    ss = d.get("start_s")
                    if ss is None:
                        continue
                    try:
                        ssv = float(ss)
                    except Exception:
                        continue
                    if ssv >= now - window:
                        count += 1
                msgs_per_sec = count / window
                last_iso = data[-1].get("ts")
            else:
                msgs_per_sec = 0.0
                last_iso = None
            collisions_info = self._compute_collisions(data) if data else {
                "per_node_collisions": {},
                "per_node_pairwise": {},
                "total_collided_messages": 0,
                "total_pairwise_overlaps": 0,
            }
            per_node_collisions = collisions_info["per_node_collisions"]
            per_node_pairwise = collisions_info["per_node_pairwise"]
            summary: Dict[str, Dict[str, float]] = {}
            for d in data:
                node = d.get("node")
                if node is None:
                    continue
                key = str(node)
                entry = summary.setdefault(
                    key,
                    {"count": 0, "energy_total": 0.0, "collisions": 0, "pairwise_collisions": 0},
                )
                entry["count"] += 1
                e = d.get("energy_j")
                if e is not None:
                    try:
                        entry["energy_total"] += float(e)
                    except Exception:
                        pass
            for key, c in per_node_collisions.items():
                entry = summary.setdefault(
                    key,
                    {"count": 0, "energy_total": 0.0, "collisions": 0, "pairwise_collisions": 0},
                )
                entry["collisions"] = c
            for key, p in per_node_pairwise.items():
                entry = summary.setdefault(
                    key,
                    {"count": 0, "energy_total": 0.0, "collisions": 0, "pairwise_collisions": 0},
                )
                entry["pairwise_collisions"] = p
            total_messages = len(data)
            agg = {
                "fires": self.stats.fires,
                "theta": self.aggregator.theta,
                "suppressed_total": self.stats.suppressed_total,
            }
            return {
                "nodes": nodes,
                "timestamps": timestamps,
                "summary": summary,
                "msgs_per_sec": msgs_per_sec,
                "aggregator": agg,
                "total_messages": total_messages,
                "total_collided_messages": collisions_info["total_collided_messages"],
                "total_pairwise_overlaps": collisions_info["total_pairwise_overlaps"],
                "collision_mode": self.collision_mode,
                "inhibition": self.inhibition.snapshot(),
                "last_updated_iso": last_iso,
            }
