from __future__ import annotations
import threading
import time
import math
import random
from datetime import datetime, timezone
from queue import Queue
from typing import Optional
from .lif import LIFSensor
from .inhibition import InhibitionState

class NodeThread(threading.Thread):
    def __init__(
        self,
        node_id: int,
        outq: Queue,
        inhibition: InhibitionState,
        step_s: float,
        accelerate: float,
        lif_leak: float,
        lif_theta: float,
        lif_rho: int,
        lif_scale: float,
        baseline_interval: int = 0,
        trace: Optional[list[float]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.node_id = int(node_id)
        self.outq = outq
        self.inhibition = inhibition
        self.step_s = float(step_s)
        self.accelerate = float(accelerate)
        self.lif_scale = float(lif_scale)
        self.baseline_interval = int(baseline_interval)
        self.trace = list(trace) if trace is not None else None
        self.lif = LIFSensor(leak=lif_leak, theta=lif_theta, rho=lif_rho)
        self._running = threading.Event()
        self._running.set()
        self._t_idx = 0
        self.total_spikes = 0
        self.suppressed_spikes = 0

    def stop(self) -> None:
        self._running.clear()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _value_from_trace(self) -> float:
        if self.trace is None or not self.trace:
            t = self._t_idx * self.step_s
            base = 50.0 + 10.0 * math.sin(2.0 * math.pi * (t / 3600.0))
            noise = random.gauss(0.0, 1.0)
            return base + noise
        i = self._t_idx % len(self.trace)
        return float(self.trace[i])

    def run(self) -> None:
        while self._running.is_set():
            v = self._value_from_trace()
            I = v * self.lif_scale
            beta = self.inhibition.current_beta()
            spike, suppressed = self.lif.step(I, beta=beta)
            payload = {
                "ts": self._now_iso(),
                "node": self.node_id,
                "value": float(v),
                "spike": int(spike),
            }
            if spike:
                self.total_spikes += 1
            if suppressed:
                self.suppressed_spikes += 1
            payload["suppressed_total"] = int(self.suppressed_spikes)
            send = False
            if spike:
                send = True
            elif self.baseline_interval > 0 and (self._t_idx % self.baseline_interval == 0):
                send = True
                payload["baseline"] = 1
            if send:
                try:
                    self.outq.put(payload, timeout=1.0)
                except Exception:
                    pass
            self._t_idx += 1
            time.sleep(self.step_s / max(1.0, self.accelerate))
