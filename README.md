Usage - how to run

Prerequisites:
- Python 3.10+ installed and available as `python` / `python3`.

Run the gateway and nodes (recommended):

1) Run the gateway only:

```bash
python3 run.py --listen-port 9000 --dashboard-port 8050
```

2) Run `edgeDev.py` to start the gateway and multiple node processes:

```bash
python3 edgeDev.py
```

The configuration in `edgeDev.py` to increase the number of nodes and their IDs/names to be updated before running.

3) Run a single node (connects to gateway at 127.0.0.1:9000):

```bash
python node.py --id 0 --name node-0 --port 9000
```
--id/--name should be unique for each node.