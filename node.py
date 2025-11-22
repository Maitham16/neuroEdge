from __future__ import annotations
import argparse
import json
import math
import random
import socket
import threading
import time
from datetime import datetime, timezone
from lif import LIFSensor

class NodeClient:
    def __init__(
        self,
        node_id: int,
        host: str,
        port: int,
        name: str,
        ip: str,
        step_s: float,
        accelerate: float,
        lif_scale: float,
        lif_theta: float,
        lif_leak: float,
        lif_refractory: int,
        baseline_interval: int,
    ) -> None:
        self.node_id = int(node_id)
        self.host = host
        self.port = int(port)
        self.name = name
        self.ip = ip
        self.step_s = float(step_s)
        self.accelerate = float(accelerate)
        self.lif_scale = float(lif_scale)
        self.baseline_interval = int(baseline_interval)
        self._lif = LIFSensor(leak=lif_leak, theta=lif_theta, refractory=lif_refractory)
        self._i = 0
        self.running = False
        self.beta = 1.0
        self.inhibited_steps = 0
        self.total_spikes = 0
        self.suppressed_total = 0
        self.sock: socket.socket | None = None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _drive_value(self) -> float:
        t = self._i * self.step_s
        base = 50.0 + 10.0 * math.sin(2.0 * math.pi * (t / 3600.0))
        noise = random.gauss(0.0, 1.0)
        return base + noise

    def _recv_loop(self) -> None:
        if self.sock is None:
            return
        f = self.sock.makefile("r")
        while self.running:
            try:
                line = f.readline()
                if not line:
                    time.sleep(0.05)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("cmd") == "inhibit":
                    self.beta = float(obj.get("beta", 1.0))
                    self.inhibited_steps = int(obj.get("t_inh", 0))
            except Exception:
                time.sleep(0.05)

    def run(self) -> None:
        self.running = True
        try:
            self.sock = socket.create_connection((self.host, self.port))
        except Exception as e:
            print(f"node {self.node_id}: connect failed to {self.host}:{self.port}: {e}")
            return
        print(f"node {self.node_id} connected to {self.host}:{self.port} name={self.name} ip={self.ip}")
        recv_t = threading.Thread(target=self._recv_loop, daemon=True)
        recv_t.start()
        try:
            while self.running:
                v = self._drive_value()
                I = float(v) * self.lif_scale
                spike, suppressed = self._lif.step(I, beta=self.beta)
                msg = {
                    "ts": self._now_iso(),
                    "node": self.node_id,
                    "name": self.name,
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
                send = False
                if spike:
                    send = True
                elif self.baseline_interval > 0 and (self._i % self.baseline_interval == 0):
                    send = True
                if send and self.sock is not None:
                    try:
                        payload = json.dumps(msg) + "\n"
                        self.sock.sendall(payload.encode("utf-8"))
                    except BrokenPipeError:
                        print(f"node {self.node_id}: connection closed by gateway")
                        break
                if self.inhibited_steps > 0:
                    self.inhibited_steps -= 1
                    if self.inhibited_steps == 0:
                        self.beta = 1.0
                self._i += 1
                time.sleep(self.step_s / max(1.0, self.accelerate))
        finally:
            self.running = False
            try:
                if self.sock is not None:
                    self.sock.close()
            except Exception:
                pass

    def stop(self) -> None:
        self.running = False

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--name", type=str, default="")
    p.add_argument("--ip", type=str, default="")
    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--step-s", type=float, default=300.0)
    p.add_argument("--accelerate", type=float, default=60.0)
    p.add_argument("--lif-theta", type=float, default=50.0)
    p.add_argument("--lif-leak", type=float, default=0.99)
    p.add_argument("--lif-scale", type=float, default=1.0)
    p.add_argument("--lif-refractory", type=int, default=0)
    p.add_argument("--baseline-interval", type=int, default=0)
    return p.parse_args()

def main() -> None:
    args = parse_args()
    if not args.name:
        args.name = f"node-{args.id}"
    if not args.ip:
        base = 10 + int(args.id)
        args.ip = f"10.0.0.{base}"
    client = NodeClient(
        node_id=args.id,
        host=args.host,
        port=args.port,
        name=args.name,
        ip=args.ip,
        step_s=args.step_s,
        accelerate=args.accelerate,
        lif_scale=args.lif_scale,
        lif_theta=args.lif_theta,
        lif_leak=args.lif_leak,
        lif_refractory=args.lif_refractory,
        baseline_interval=args.baseline_interval,
    )
    try:
        client.run()
    except KeyboardInterrupt:
        client.stop()

if __name__ == "__main__":
    main()