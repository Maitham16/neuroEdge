from __future__ import annotations
import argparse
import threading
import time
import signal
import sys
from queue import Queue
from inhibition import InhibitionState
from gateway import Gateway
from dashboard import run_http
from node import Node

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--nodes", type=int, default=10)
    p.add_argument("--step-s", type=float, default=300.0)
    p.add_argument("--accelerate", type=float, default=60.0)
    p.add_argument("--lif-theta", type=float, default=50.0)
    p.add_argument("--lif-scale", type=float, default=1.0)
    p.add_argument("--lif-leak", type=float, default=0.99)
    p.add_argument("--lif-refractory", type=int, default=0)
    p.add_argument("--baseline-interval", type=int, default=0)
    p.add_argument("--agg-leak", type=float, default=0.995)
    p.add_argument("--agg-theta", type=float, default=10.0)
    p.add_argument("--beta", type=float, default=2.0)
    p.add_argument("--t-inh", type=int, default=5)
    p.add_argument("--dashboard-host", type=str, default="127.0.0.1")
    p.add_argument("--dashboard-port", type=int, default=8050)
    p.add_argument("--duration-s", type=float, default=0.0)
    return p.parse_args()

def main():
    args = parse_args()
    q: Queue = Queue()
    effective_step = args.step_s / max(1.0, args.accelerate)
    inhibition = InhibitionState(step_s=effective_step)
    gateway = Gateway(
        inq=q,
        inhibition=inhibition,
        agg_leak=args.agg_leak,
        agg_theta=args.agg_theta,
        beta=args.beta,
        t_inh_steps=args.t_inh,
        tx_power_w=0.396,
        payload_bytes=12,
        collision_mode="spikes",
    )
    gw_thread = threading.Thread(target=gateway.run, kwargs={"timeout": 0.5}, daemon=True)
    gw_thread.start()
    http_thread = threading.Thread(target=run_http, args=(gateway, args.dashboard_host, args.dashboard_port), daemon=True)
    http_thread.start()
    nodes: list[Node] = []
    for i in range(args.nodes):
        n = Node(
            node_id=i,
            outq=q,
            inhibition=inhibition,
            step_s=args.step_s,
            accelerate=args.accelerate,
            lif_scale=args.lif_scale,
            lif_theta=args.lif_theta,
            lif_leak=args.lif_leak,
            lif_refractory=args.lif_refractory,
            baseline_interval=args.baseline_interval,
            ip=None,
        )
        n.start()
        nodes.append(n)
    print("Gateway running on http://%s:%d/ nodes=%d" % (args.dashboard_host, args.dashboard_port, args.nodes))
    def shutdown(signum=None, frame=None):
        gateway.stop()
        for n in nodes:
            n.stop()
        time.sleep(0.5)
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    if args.duration_s > 0:
        time.sleep(args.duration_s)
        shutdown()
    else:
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            shutdown()

if __name__ == "__main__":
    main()
