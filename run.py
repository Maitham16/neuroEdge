from __future__ import annotations
import argparse
import threading
import time
from queue import Queue
from .inhibition import InhibitionState
from .gateway import Gateway
from .node import NodeThread
from .dashboard import run_http

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--nodes", type=int, default=10)
    p.add_argument("--step-s", type=float, default=300.0)
    p.add_argument("--accelerate", type=float, default=60.0)
    p.add_argument("--lif-leak", type=float, default=0.99)
    p.add_argument("--lif-theta", type=float, default=20.0)
    p.add_argument("--lif-rho", type=int, default=0)
    p.add_argument("--lif-scale", type=float, default=1.0)
    p.add_argument("--agg-leak", type=float, default=0.99)
    p.add_argument("--agg-theta", type=float, default=50.0)
    p.add_argument("--beta", type=float, default=2.0)
    p.add_argument("--t-inh-steps", type=int, default=12)
    p.add_argument("--collision-mode", type=str, choices=["all", "spikes"], default="spikes")
    p.add_argument("--retention-multiplier", type=float, default=10.0)
    p.add_argument("--min-retention-s", type=float, default=2.0)
    p.add_argument("--tx-power-w", type=float, default=0.396)
    p.add_argument("--payload-bytes", type=int, default=12)
    p.add_argument("--baseline-interval", type=int, default=0)
    p.add_argument("--dashboard-port", type=int, default=8050)
    p.add_argument("--http-host", type=str, default="")
    p.add_argument("--duration-s", type=float, default=0.0)
    return p.parse_args()

def main() -> None:
    args = parse_args()
    q: Queue = Queue()
    inhibition = InhibitionState(step_s=args.step_s)
    gateway = Gateway(
        inq=q,
        inhibition=inhibition,
        agg_leak=args.agg_leak,
        agg_theta=args.agg_theta,
        beta=args.beta,
        t_inh_steps=args.t_inh_steps,
        tx_power_w=args.tx_power_w,
        payload_bytes=args.payload_bytes,
        collision_mode=args.collision_mode,
        retention_multiplier=args.retention_multiplier,
        min_retention_s=args.min_retention_s,
    )
    gw_thread = threading.Thread(target=gateway.run, kwargs={"timeout": 0.5}, daemon=True)
    gw_thread.start()
    nodes = []
    for i in range(args.nodes):
        node = NodeThread(
            node_id=i,
            outq=q,
            inhibition=inhibition,
            step_s=args.step_s,
            accelerate=args.accelerate,
            lif_leak=args.lif_leak,
            lif_theta=args.lif_theta,
            lif_rho=args.lif_rho,
            lif_scale=args.lif_scale,
            baseline_interval=args.baseline_interval,
        )
        node.start()
        nodes.append(node)
    http_thread = threading.Thread(target=run_http, args=(gateway, args.http_host, args.dashboard_port), daemon=True)
    http_thread.start()
    print("Dashboard http://127.0.0.1:%d/" % args.dashboard_port)
    try:
        if args.duration_s > 0:
            time.sleep(args.duration_s)
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        for n in nodes:
            n.stop()
        gateway.stop()
        time.sleep(0.5)

if __name__ == "__main__":
    main()
