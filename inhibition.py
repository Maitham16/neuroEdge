from __future__ import annotations
import threading
import time

class InhibitionState:
    def __init__(self, step_s: float) -> None:
        self._lock = threading.Lock()
        self._beta = 1.0
        self._expiry_ts = 0.0
        self.step_s = float(step_s)

    def current_beta(self) -> float:
        with self._lock:
            if self._expiry_ts and time.time() >= self._expiry_ts:
                self._beta = 1.0
                self._expiry_ts = 0.0
            return self._beta

    def activate(self, beta: float, steps: int) -> None:
        with self._lock:
            self._beta = float(beta)
            self._expiry_ts = time.time() + max(0, int(steps)) * self.step_s

    def snapshot(self) -> dict:
        with self._lock:
            return {"beta": self._beta, "expiry_ts": self._expiry_ts}
