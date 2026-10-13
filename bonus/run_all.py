"""Run every offline-safe bonus and write evidence artifacts."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bonus.docker import exporter
from bonus.litellm_tracker import demo as tracker_demo
from bonus.local_model import run_local


def main() -> int:
    os.makedirs(os.path.join(ROOT, "outputs"), exist_ok=True)
    if tracker_demo.main() != 0:
        return 1
    if run_local.main(["--backend", "builtin", "--tokens", "50000"]) != 0:
        return 1

    metrics = exporter.render()
    metrics_path = os.path.join(ROOT, "outputs", "bonus_prometheus_metrics.txt")
    with open(metrics_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(metrics)

    dashboard_path = os.path.join(ROOT, "bonus", "docker", "grafana", "dashboards", "gpu_cost.json")
    with open(dashboard_path, encoding="utf-8") as handle:
        dashboard = json.load(handle)
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    required_metrics = {
        "gpu_util_pct",
        "gpu_mfu",
        "gpu_wasted_cost_usd_per_hr",
        "gpu_power_w",
        "gpu_carbon_g_per_hr",
    }
    if not required_metrics.issubset(expressions) or not all(metric in metrics for metric in required_metrics):
        raise RuntimeError("Grafana dashboard and exporter metrics are out of sync")

    with open(os.path.join(ROOT, "outputs", "bonus_litellm_tracker.json"), encoding="utf-8") as handle:
        tracker = json.load(handle)
    with open(os.path.join(ROOT, "outputs", "bonus_local_model.json"), encoding="utf-8") as handle:
        local = json.load(handle)

    summary = "\n".join([
        "# Bonus completion evidence",
        "",
        "**Student:** Trần Thu Phương",
        "",
        "**Student ID:** 2A202602366",
        "",
        "| Bonus | Measured evidence | Artifact |",
        "|---|---|---|",
        (
            f"| LiteLLM-style tracker | {tracker['requests_logged']} accepted requests; "
            f"budget guard triggered: {tracker['budget_guard_triggered']} | "
            "`bonus_litellm_tracker.json` |"
        ),
        (
            f"| Local CPU model | {local['tokens_per_second']:,.1f} tok/s; "
            f"${local['cost_usd_per_million_tokens']:,.6f}/1M tokens | "
            "`bonus_local_model.json` |"
        ),
        (
            f"| Prometheus + Grafana | {len(required_metrics)} validated metrics and "
            f"{len(dashboard['panels'])} dashboard panels | `bonus_prometheus_metrics.txt` |"
        ),
        "",
        "The Docker stack is defined in `bonus/docker/docker-compose.yml`; the exporter "
        "path is also testable without Docker so grading remains offline-safe.",
        "",
    ])
    summary_path = os.path.join(ROOT, "outputs", "bonus_summary.md")
    with open(summary_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(summary)
    print("Prometheus metrics:", len(metrics.splitlines()), "lines")
    print("Grafana panels:", len(dashboard["panels"]))
    print("artifact: outputs/bonus_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
