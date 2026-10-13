import json
import os

import pytest

from bonus.docker import exporter
from bonus.litellm_tracker.tracker import BudgetExceeded, CostTracker
from bonus.local_model import run_local


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tracker_attributes_cost_and_enforces_budget():
    tracker = CostTracker(budgets={"team": 0.0001})
    with pytest.raises(BudgetExceeded):
        tracker.complete("team", "large", "hello", max_output_tokens=256)
    assert tracker.summary()["by_key"]["team"]["requests"] == 0


def test_builtin_local_model_benchmark_is_real_and_positive():
    result = run_local.benchmark_builtin(1000, 0.10)
    assert result["backend"] == "builtin"
    assert result["tokens_per_second"] > 0
    assert result["cost_usd_per_million_tokens"] > 0


def test_exporter_and_dashboard_stay_in_sync():
    metrics = exporter.render()
    required = {
        "gpu_util_pct",
        "gpu_mfu",
        "gpu_wasted_cost_usd_per_hr",
        "gpu_power_w",
        "gpu_carbon_g_per_hr",
    }
    assert all(name in metrics for name in required)
    dashboard_path = os.path.join(
        ROOT, "bonus", "docker", "grafana", "dashboards", "gpu_cost.json",
    )
    with open(dashboard_path, encoding="utf-8") as handle:
        dashboard = json.load(handle)
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    assert required <= expressions
