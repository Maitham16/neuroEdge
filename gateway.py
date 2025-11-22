from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from queue import Queue, Empty
from threading import Event, Lock
from typing import Any, Dict, Optional, Callable
from lif import LIFAggregator
from inhibition import InhibitionState

@dataclass
class GatewayStats:
    fires: int = 0
    suppressed_total: int = 0

class Gateway:
    def __init__(
        self,
        inq: Queue,
        inhibition: InhibitionState,
        agg_leak: float = 0.995,
        agg_theta: float = 10.0,
        beta: float = 2.0,
        t_inh_steps: int = 5,
        tx_power_w: float = 0.396,
        payload_bytes: int = 12,
        collision_mode: str = "spikes",
        retention_multiplier: float = 10.0,
        min_retention_s: float = 2.0,
        max_recent: int = 5000,
        on_fire: Optional[Callable[[float, int], None]] = None,
    ) -> None:
        self.inq = inq
        self.inhibition = inhibition
        self.aggregator = LIFAggregator(leak=agg_leak, theta=agg_theta)
        self.beta = float(beta)
        self.t_inh_steps = int(t_inh_steps)
        self.tx_power_w = float(tx_power_w)
        self.payload_bytes = int(payload_bytes)
        self.collision_mode = str(collision_mode)
        self.retention_multiplier = float(retention_multiplier)
        self.min_retention_s = float(min_retention_s)
        self._recent_msgs: deque[Dict[str, Any]] = deque(maxlen=max_recent)
        self._recent_tx: list[Dict[str, Any]] = []
        self._total_messages = 0
        self._total_collided_messages = 0
        self._total_pairwise_overlaps = 0
        self._per_node_collisions: Dict[int, int] = {}
        self._per_node_pairwise: Dict[int, int] = {}
        self._per_node_suppressed: Dict[int, int] = {}
        self.stats = GatewayStats()
        self._lock = Lock()
        self._stop = Event()
        self._on_fire = on_fire

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
                if self._on_fire is not None:
                    self._on_fire(self.beta, self.t_inh_steps)
        node_raw = msg.get("node")
        try:
            node_id = int(node_raw)
        except Exception:
            node_id = None
        st = msg.get("suppressed_total")
        if st is not None and node_id is not None:
            try:
                st_int = int(st)
            except Exception:
                st_int = None
            if st_int is not None:
                prev = self._per_node_suppressed.get(node_id, 0)
                if st_int != prev:
                    self._per_node_suppressed[node_id] = st_int
                    self.stats.suppressed_total = sum(self._per_node_suppressed.values())
        self._recent_msgs.append(msg)
        self._total_messages += 1
        if node_id is None:
            return
        if self.collision_mode == "spikes":
            is_tx = spike_flag
        else:
            is_tx = True
        new_entry = {
            "node": node_id,
            "start": start_s,
            "end": end_s,
            "is_tx": bool(is_tx),
            "collided": False,
        }
        if is_tx:
            overlaps: list[Dict[str, Any]] = []
            for ent in self._recent_tx:
                if not ent.get("is_tx", False):
                    continue
                if ent.get("node") == node_id:
                    continue
                s = float(ent.get("start", 0.0))
                e = float(ent.get("end", 0.0))
                if e <= start_s or s >= end_s:
                    continue
                overlaps.append(ent)
            if overlaps:
                self._total_pairwise_overlaps += len(overlaps)
                for ent in overlaps:
                    other = int(ent["node"])
                    self._per_node_pairwise[other] = self._per_node_pairwise.get(other, 0) + 1
                    if not ent.get("collided", False):
                        ent["collided"] = True
                        self._total_collided_messages += 1
                        self._per_node_collisions[other] = self._per_node_collisions.get(other, 0) + 1
                new_entry["collided"] = True
                self._total_collided_messages += 1
                self._per_node_collisions[node_id] = self._per_node_collisions.get(node_id, 0) + 1
                self._per_node_pairwise[node_id] = self._per_node_pairwise.get(node_id, 0) + len(overlaps)
        self._recent_tx.append(new_entry)
        cutoff = time.time() - max(self.min_retention_s, airtime * self.retention_multiplier)
        self._recent_tx = [t for t in self._recent_tx if float(t.get("end", 0.0)) >= cutoff]

    def loop_once(self, timeout: float = 0.5):
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
            nodes: Dict[str, Dict[str, Any]] = {}
            for key, series in nodes_values.items():
                nodes[key] = {"values": [series.get(ts) for ts in timestamps]}
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
            for node_int, c in self._per_node_collisions.items():
                key = str(node_int)
                entry = summary.setdefault(
                    key,
                    {"count": 0, "energy_total": 0.0, "collisions": 0, "pairwise_collisions": 0},
                )
                entry["collisions"] = c
            for node_int, p in self._per_node_pairwise.items():
                key = str(node_int)
                entry = summary.setdefault(
                    key,
                    {"count": 0, "energy_total": 0.0, "collisions": 0, "pairwise_collisions": 0},
                )
                entry["pairwise_collisions"] = p
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
                "total_messages": self._total_messages,
                "total_collided_messages": self._total_collided_messages,
                "total_pairwise_overlaps": self._total_pairwise_overlaps,
                "collision_mode": self.collision_mode,
                "inhibition": self.inhibition.snapshot(),
                "last_updated_iso": last_iso,
            }