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
        self._recent_transmissions: List[Dict[str, Any]] = []
        self._per_node_energy: Dict[int, float] = {}
        self._per_node_collisions: Dict[int, int] = {}
        self._per_node_pairwise: Dict[int, int] = {}
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

    def _update_collisions(self, msg: Dict[str, Any], start_s: float, end_s: float, is_spike: bool) -> None:
        node = msg.get("node")
        if node is None:
            return
        node_int = int(node)
        overlaps: List[Dict[str, Any]] = []
        for entry in list(self._recent_transmissions):
            s = entry.get("start_s")
            e = entry.get("end_s")
            other_node = entry.get("node")
            other_spike = bool(entry.get("spike", False))
            if e is None or s is None:
                continue
            if e <= start_s or s >= end_s:
                continue
            if other_node == node_int:
                continue
            if self.collision_mode == "spikes":
                if not (is_spike and other_spike):
                    continue
            overlaps.append(entry)
        pair_count = len(overlaps)
        msg["pairwise_collisions"] = pair_count
        collided = pair_count > 0
        msg["collided"] = collided
        for entry in overlaps:
            other_node = int(entry.get("node"))
            self._per_node_pairwise[other_node] = self._per_node_pairwise.get(other_node, 0) + 1
            if not entry.get("collided_reported"):
                entry["collided_reported"] = True
                self._per_node_collisions[other_node] = self._per_node_collisions.get(other_node, 0) + 1
        if collided:
            self._per_node_collisions[node_int] = self._per_node_collisions.get(node_int, 0) + 1
            self._per_node_pairwise[node_int] = self._per_node_pairwise.get(node_int, 0) + pair_count
        entry = {
            "node": node_int,
            "start_s": start_s,
            "end_s": end_s,
            "spike": bool(is_spike),
            "collided_reported": collided,
        }
        self._recent_transmissions.append(entry)
        cutoff = time.time() - max(self.min_retention_s, (end_s - start_s) * self.retention_multiplier)
        self._recent_transmissions = [t for t in self._recent_transmissions if t.get("end_s", 0.0) >= cutoff]

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
        node = msg.get("node")
        if node is not None:
            node_int = int(node)
            self._per_node_energy[node_int] = self._per_node_energy.get(node_int, 0.0) + energy
        spike_flag = int(msg.get("spike", 0)) == 1
        self._update_collisions(msg, start_s, end_s, spike_flag)
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

    def snapshot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            data = list(self._recent_msgs)
            timestamps = [d.get("ts") for d in data]
            nodes_values: Dict[str, Dict[str, float]] = {}
            for d in data:
                ts = d.get("ts")
                node = str(d.get("node"))
                if ts is None or node is None:
                    continue
                nodes_values.setdefault(node, {})
                try:
                    nodes_values[node][ts] = float(d.get("value", 0.0))
                except Exception:
                    nodes_values[node][ts] = 0.0
            nodes = {}
            for node, series in nodes_values.items():
                nodes[node] = {"values": [series.get(ts) for ts in timestamps]}
            summary: Dict[str, Dict[str, float]] = {}
            for node_str, energy in self._per_node_energy.items():
                key = str(node_str)
                summary.setdefault(key, {})
                summary[key]["energy_total"] = energy
            for node_int, coll in self._per_node_collisions.items():
                key = str(node_int)
                summary.setdefault(key, {})
                summary[key]["collisions"] = coll
            for node_int, pair in self._per_node_pairwise.items():
                key = str(node_int)
                summary.setdefault(key, {})
                summary[key]["pairwise_collisions"] = pair
            for node_str in nodes.keys():
                if node_str not in summary:
                    summary[node_str] = {}
            for node_str in nodes.keys():
                count = sum(1 for d in data if str(d.get("node")) == node_str)
                entry = summary.setdefault(node_str, {})
                entry.setdefault("energy_total", 0.0)
                entry.setdefault("collisions", 0)
                entry.setdefault("pairwise_collisions", 0)
                entry["count"] = count
            if data:
                now = time.time()
                window = 60.0
                count = 0
                for d in data:
                    ss = d.get("start_s")
                    if ss is None:
                        continue
                    if float(ss) >= now - window:
                        count += 1
                msgs_per_sec = count / window
                last_iso = data[-1].get("ts")
            else:
                msgs_per_sec = 0.0
                last_iso = None
            total_messages = len(data)
            total_collisions = sum(self._per_node_collisions.values()) if self._per_node_collisions else 0
            total_pairwise = sum(self._per_node_pairwise.values()) if self._per_node_pairwise else 0
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
                "total_collided_messages": total_collisions,
                "total_pairwise_overlaps": total_pairwise,
                "collision_mode": self.collision_mode,
                "inhibition": self.inhibition.snapshot(),
                "last_updated_iso": last_iso,
            }
