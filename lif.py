from __future__ import annotations
from dataclasses import dataclass

@dataclass
class LIFState:
    u: float = 0.0
    r: int = 0

class LIFSensor:
    def __init__(self, leak: float, theta: float, rho: int) -> None:
        self.leak = float(leak)
        self.theta_base = float(theta)
        self.theta = float(theta)
        self.rho = int(rho)
        self.state = LIFState()

    def reset(self) -> None:
        self.state = LIFState()
        self.theta = self.theta_base

    def step(self, I: float, beta: float = 1.0) -> tuple[int, int]:
        u_prev = self.state.u
        u_new = self.leak * u_prev + float(I)
        self.state.u = u_new
        if self.state.r > 0:
            self.state.r -= 1
            return 0, 0
        theta_eff = self.theta_base * float(beta)
        spike = 0
        suppressed = 0
        if u_new >= theta_eff:
            spike = 1
            self.state.u = 0.0
            if self.rho > 0:
                self.state.r = self.rho
        else:
            if beta > 1.0 and self.theta_base <= u_new < theta_eff:
                suppressed = 1
        return spike, suppressed

class LIFAggregator:
    def __init__(self, leak: float, theta: float) -> None:
        self.leak = float(leak)
        self.theta = float(theta)
        self.v = 0.0

    def reset(self) -> None:
        self.v = 0.0

    def step(self, x: float) -> int:
        self.v = self.leak * self.v + float(x)
        if self.v >= self.theta:
            self.v = 0.0
            return 1
        return 0
