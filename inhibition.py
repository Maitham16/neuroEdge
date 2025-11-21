from __future__ import annotations
from dataclasses import dataclass, field
from threading import Lock
import time

@dataclass
class InhibitionState:
    beta: float = 1.0
    expiry_ts: float = 0.0
    step_s: float = 1.0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def activate(self, beta: float, t_inh_steps: int) -> None:
        with self._lock:
            self.beta = float(beta)
            self.expiry_ts = time.time() + max(0, int(t_inh_steps)) * float(self.step_s)

    def current_beta(self) -> float:
        with self._lock:
            if self.expiry_ts <= time.time():
                return 1.0
            return self.beta

    def snapshot(self) -> dict:
        with self._lock:
            if self.expiry_ts <= time.time():
                b = 1.0
            else:
                b = self.beta
            return {"beta": float(b), "expiry_ts": float(self.expiry_ts)}