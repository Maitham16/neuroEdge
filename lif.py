from __future__ import annotations
from dataclasses import dataclass

@dataclass
class LIFConfig:
    leak: float = 0.99
    theta: float = 50.0
    refractory: int = 0

class LIFSensor:
    def __init__(self, leak: float = 0.99, theta: float = 50.0, refractory: int = 0):
        self.leak = float(leak)
        self.theta_base = float(theta)
        self.theta = float(theta)
        self.refractory = int(refractory)
        self.u = 0.0
        self._r = 0

    def reset(self) -> None:
        self.u = 0.0
        self._r = 0

    def step(self, I: float, beta: float = 1.0) -> tuple[bool, bool]:
        if self._r > 0:
            self._r -= 1
            return False, False
        self.theta = self.theta_base * float(beta)
        u_before = float(self.u)
        u_candidate = self.leak * u_before + float(I)
        theta_eff = self.theta
        if u_candidate >= theta_eff:
            self.u = 0.0
            self._r = self.refractory
            return True, False
        suppressed = False
        if beta > 1.0 and u_candidate >= self.theta_base and u_candidate < theta_eff:
            suppressed = True
        self.u = u_candidate
        return False, suppressed

class LIFAggregator:
    def __init__(self, leak: float = 0.995, theta: float = 10.0, refractory: int = 0):
        self.leak = float(leak)
        self.theta = float(theta)
        self.refractory = int(refractory)
        self.v = 0.0
        self._r = 0

    def reset(self) -> None:
        self.v = 0.0
        self._r = 0

    def step(self, input_strength: float = 1.0) -> bool:
        if self._r > 0:
            self._r -= 1
            return False
        self.v = self.leak * self.v + float(input_strength)
        if self.v >= self.theta:
            self.v = 0.0
            self._r = self.refractory
            return True
        return False