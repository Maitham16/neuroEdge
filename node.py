from __future__ import annotations
import threading
import time
import math
import random
from datetime import datetime, timezone
from queue import Queue
from typing import Optional
from lif import LIFSensor
from inhibition import InhibitionState

class Node(threading.Thread):
    def __init__(
        self,
        node_id: int,
        outq: Queue,
        inhibition: InhibitionState,
        step_s: float = 300.0,
        accelerate: float = 60.0,
        lif_scale: float = 1.0,
        lif_theta: float = 50.0,
        lif_leak: float = 0.99,
        lif_refractory: int = 0,
        baseline_interval: int = 0,
        ip: Optional[str] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.node_id = int(node_id)
        self.ip = ip or f"10.0.0.{10 + self.node_id}"
        self.outq = outq
        self.inhibition = inhibition
        self.step_s = float(step_s)
        self.accelerate = float(accelerate)
        self.lif_scale = float(lif_scale)
        self.baseline_interval = int(baseline_interval)
        self._lif = LIFSensor(leak=lif_leak, theta=lif_theta, refractory=lif_refractory)
        self._i = 0
        self.running = False
        self.total_spikes = 0
        self.suppressed_total = 0

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _drive_value(self) -> float:
        t = self._i * self.step_s
        base = 50.0 + 10.0 * math.sin(2.0 * math.pi * (t / 3600.0))
        noise = random.gauss(0.0, 1.0)
        return base + noise

    def run(self) -> None:
        self.running = True
        while self.running:
            v = self._drive_value()
            beta = self.inhibition.current_beta()
            I = float(v) * self.lif_scale
            spike, suppressed = self._lif.step(I, beta=beta)
            msg = {
                "ts": self._now_iso(),
                "node": self.node_id,
                "ip": self.ip,
                "value": float(v),
            }
            if spike:
                msg["spike"] = 1
                self.total_spikes += 1
            else:
                msg["spike"] = 0
            if suppressed:
                self.suppressed_total += 1
            msg["suppressed_total"] = int(self.suppressed_total)
            if self.baseline_interval <= 0 or spike or (self._i % self.baseline_interval == 0):
                self.outq.put(msg)
            self._i += 1
            time.sleep(self.step_s / max(1.0, self.accelerate))

    def stop(self) -> None:
        self.running = False