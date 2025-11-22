from __future__ import annotations
import argparse
import json
import signal
import socketserver
import sys
import threading
import time
from queue import Queue
from typing import Dict
from inhibition import InhibitionState
from gateway import Gateway
from dashboard import run_http

_clients_lock = threading.Lock()
_clients: Dict[int, "GatewayHandler"] = {}
_inq: Queue = Queue()

class GatewayHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        global _clients
        node_id = None
        peer = self.client_address
        print(f"gateway: connection from {peer}")
        try:
            for raw in self.rfile:
                try:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                except Exception:
                    continue
                try:
                    nid = int(obj.get("node"))
                except Exception:
                    nid = None
                if nid is not None and node_id is None:
                    node_id = nid
                    with _clients_lock:
                        _clients[nid] = self
                _inq.put(obj)
        finally:
            if node_id is not None:
                with _clients_lock:
                    _clients.pop(node_id, None)
                print(f"gateway: node {node_id} disconnected")

def _broadcast_inhibit(beta: float, t_inh: int) -> None:
    cmd = json.dumps({"cmd": "inhibit", "beta": float(beta), "t_inh": int(t_inh)}) + "\n"
    data = cmd.encode("utf-8")
    with _clients_lock:
        for nid, handler in list(_clients.items()):
            try:
                handler.wfile.write(data)
                handler.wfile.flush()
            except Exception:
                pass

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--listen-host", type=str, default="0.0.0.0")
    p.add_argument("--listen-port", type=int, default=9000)
    p.add_argument("--dashboard-host", type=str, default="127.0.0.1")
    p.add_argument("--dashboard-port", type=int, default=8050)
    p.add_argument("--agg-leak", type=float, default=0.995)
    p.add_argument("--agg-theta", type=float, default=10.0)
    p.add_argument("--beta", type=float, default=2.0)
    p.add_argument("--t-inh", type=int, default=5)
    p.add_argument("--step-real-s", type=float, default=5.0)
    return p.parse_args()

def main() -> None:
    args = parse_args()
    inhibition = InhibitionState(step_s=float(args.step_real_s))
    gateway = Gateway(
        inq=_inq,
        inhibition=inhibition,
        agg_leak=args.agg_leak,
        agg_theta=args.agg_theta,
        beta=args.beta,
        t_inh_steps=args.t_inh,
        tx_power_w=0.396,
        payload_bytes=12,
        collision_mode="spikes",
        on_fire=_broadcast_inhibit,
    )
    gw_thread = threading.Thread(target=gateway.run, kwargs={"timeout": 0.5}, daemon=True)
    gw_thread.start()
    http_thread = threading.Thread(target=run_http, args=(gateway, args.dashboard_host, args.dashboard_port), daemon=True)
    http_thread.start()
    server = socketserver.ThreadingTCPServer((args.listen_host, args.listen_port), GatewayHandler)
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()
    print(f"gateway: TCP listen on {args.listen_host}:{args.listen_port}")
    print(f"gateway: dashboard http://{args.dashboard_host}:{args.dashboard_port}/")
    def shutdown(signum=None, frame=None) -> None:
        print("gateway: shutting down")
        gateway.stop()
        try:
            server.shutdown()
        except Exception:
            pass
        time.sleep(0.5)
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        shutdown()

if __name__ == "__main__":
    main()