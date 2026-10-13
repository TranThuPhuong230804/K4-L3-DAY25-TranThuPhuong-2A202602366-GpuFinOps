"""Pure-stdlib Prometheus exporter: turns the synthetic telemetry into GPU cost
metrics. Runnable with or without Docker:  python bonus/docker/exporter.py
Then scrape http://localhost:9101/metrics
"""
from __future__ import annotations
import csv, os
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

DATA_DIR = os.environ.get("LAB_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"))
GRID_CARBON_G_PER_KWH = float(os.environ.get("GRID_CARBON_G_PER_KWH", "380"))


def _load():
    cat = {}
    with open(os.path.join(DATA_DIR, "price_catalog.csv")) as f:
        for r in csv.DictReader(f):
            cat[r["gpu_type"]] = r
    agg = defaultdict(lambda: {"util": [], "mfu": [], "power": [], "type": None})
    with open(os.path.join(DATA_DIR, "gpu_telemetry.csv")) as f:
        for r in csv.DictReader(f):
            a = agg[r["gpu_id"]]
            a["type"] = r["gpu_type"]
            peak = float(cat[r["gpu_type"]]["peak_tflops_fp16"]) or 1.0
            a["util"].append(float(r["gpu_util_pct"]))
            a["mfu"].append(float(r["achieved_tflops"]) / peak)
            a["power"].append(float(r["power_w"]))
    return cat, agg


def render() -> str:
    cat, agg = _load()
    out = [
        "# HELP gpu_util_pct nvidia-smi time-active utilization",
        "# TYPE gpu_util_pct gauge",
        "# HELP gpu_mfu Model FLOPs Utilization (real efficiency)",
        "# TYPE gpu_mfu gauge",
        "# HELP gpu_hourly_cost_usd on-demand $/GPU-hr",
        "# TYPE gpu_hourly_cost_usd gauge",
        "# HELP gpu_wasted_cost_usd_per_hr $/hr paid for FLOPs not used (1-mfu)*cost",
        "# TYPE gpu_wasted_cost_usd_per_hr gauge",
        "# HELP gpu_power_w Average GPU board power",
        "# TYPE gpu_power_w gauge",
        "# HELP gpu_carbon_g_per_hr Estimated operational carbon at configured grid intensity",
        "# TYPE gpu_carbon_g_per_hr gauge",
    ]
    for gid, a in agg.items():
        gtype = a["type"]
        util = sum(a["util"]) / len(a["util"])
        mfu = sum(a["mfu"]) / len(a["mfu"])
        cost = float(cat[gtype]["on_demand_hr"])
        wasted = (1.0 - mfu) * cost
        power = sum(a["power"]) / len(a["power"])
        carbon = power / 1000.0 * GRID_CARBON_G_PER_KWH
        lbl = f'{{gpu_id="{gid}",gpu_type="{gtype}"}}'
        out.append(f"gpu_util_pct{lbl} {util:.2f}")
        out.append(f"gpu_mfu{lbl} {mfu:.4f}")
        out.append(f"gpu_hourly_cost_usd{lbl} {cost:.2f}")
        out.append(f"gpu_wasted_cost_usd_per_hr{lbl} {wasted:.4f}")
        out.append(f"gpu_power_w{lbl} {power:.2f}")
        out.append(f"gpu_carbon_g_per_hr{lbl} {carbon:.4f}")
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if self.path != "/metrics":
            self.send_response(404); self.end_headers(); return
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9101"))
    print(f"GPU cost exporter on :{port}/metrics  (data: {DATA_DIR})")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
