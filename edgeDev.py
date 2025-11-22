from __future__ import annotations
import subprocess
import sys
import time
import signal
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9000

NODE_STEP_S = 300.0
NODE_ACCELERATE = 60.0
LIF_THETA = 50.0
LIF_LEAK = 0.99
LIF_SCALE = 1.0
LIF_REFRACTORY = 0
BASELINE_INTERVAL = 0
NODE_STAGGER_S = 0.5

NODE_CONFIG = [
    {"id": 60, "name": "node-60"},
    {"id": 61, "name": "node-61"},
    {"id": 62, "name": "node-62"},
    {"id": 63, "name": "node-63"},
    {"id": 64, "name": "node-64"},
]

PROCS: list[subprocess.Popen] = []


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            s.close()
            time.sleep(0.2)
    return False


def start_node(node_id: int, name: str) -> subprocess.Popen:
    cmd = [
        sys.executable,
        str(ROOT / "node.py"),
        "--id",
        str(node_id),
        "--name",
        name,
        "--host",
        GATEWAY_HOST,
        "--port",
        str(GATEWAY_PORT),
        "--step-s",
        str(NODE_STEP_S),
        "--accelerate",
        str(NODE_ACCELERATE),
        "--lif-theta",
        str(LIF_THETA),
        "--lif-leak",
        str(LIF_LEAK),
        "--lif-scale",
        str(LIF_SCALE),
        "--lif-refractory",
        str(LIF_REFRACTORY),
        "--baseline-interval",
        str(BASELINE_INTERVAL),
    ]
    p = subprocess.Popen(cmd, cwd=str(ROOT))
    PROCS.append(p)
    return p


def shutdown(signum=None, frame=None) -> None:
    for p in PROCS[::-1]:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    time.sleep(0.5)
    for p in PROCS[::-1]:
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if not wait_for_port(GATEWAY_HOST, GATEWAY_PORT, 10.0):
        print(f"gateway {GATEWAY_HOST}:{GATEWAY_PORT} not reachable")
        sys.exit(1)

    for cfg in NODE_CONFIG:
        start_node(cfg["id"], cfg["name"])
        time.sleep(NODE_STAGGER_S)

    print(f"started {len(NODE_CONFIG)} nodes against {GATEWAY_HOST}:{GATEWAY_PORT}")
    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    main()