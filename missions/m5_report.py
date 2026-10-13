"""M5 - Build the complete baseline-vs-optimized submission report.

Run: python missions/m5_report.py -> outputs/report.md + outputs/savings.png
"""
from __future__ import annotations

import json
import os
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

try:
    # Windows PowerShell may otherwise expose a legacy cp1252 stdout stream.
    _sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from finops import report, sustainability
from missions import (
    m1_efficiency_audit,
    m2_inference_levers,
    m3_purchasing,
    m4_allocation,
)
from missions._common import ROOT

DAYS = 30
STUDENT_NAME = "Trần Thu Phương"
STUDENT_ID = "2A202602366"


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _details_markdown(r1: dict, r2: dict, r3: dict, r4: dict) -> str:
    lines = [
        "",
        "## Unit economics",
        "",
        "| Metric | Baseline | Optimized | Change |",
        "|---|---:|---:|---:|",
        (
            f"| Inference cost / 1M tokens | ${r2['baseline_per_m']:.3f} | "
            f"${r2['optimized_per_m']:.3f} | -{r2['savings_pct']:.1f}% |"
        ),
        (
            f"| Daily inference spend | {_money(r2['baseline_daily'])} | "
            f"{_money(r2['optimized_daily'])} | "
            f"-{_money(r2['baseline_daily'] - r2['optimized_daily'])} |"
        ),
        "",
        "The unit metric is the decision metric: a lower hourly GPU price is not an "
        "optimization if throughput falls enough to increase $/1M-token.",
        "",
        "## Extension 1 — Risk- and term-aware purchasing",
        "",
        (
            f"The original duty-cycle-only policy saves **{r3['simple_savings_pct']:.1f}%**; "
            f"the enhanced policy saves **{r3['savings_pct']:.1f}%** after GPU-specific "
            "interruption/rework and 1-year-versus-3-year commitment costs. "
            f"Although both round to the same tenth of a percent, the enhanced policy is "
            f"**${r3['policy_improvement_usd']:,.2f}/month better "
            f"({r3['policy_improvement_pp']:+.3f} percentage points)**."
        ),
        "",
        "| Workload | GPU | Tier | Commitment | Interrupt risk | On-demand | Optimized |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in r3["recommendations"]:
        lines.append(
            f"| {row['job_id']} | {row['gpu_type']} | {row['tier']} | "
            f"{row['commitment']} | {row['interruption_rate_pct']:.1f}% | "
            f"${row['on_demand']:,.0f} | ${row['optimized']:,.0f} |"
        )

    lie = next((row for row in r1["lies"] if row["gpu_id"] == "gpu-h100-4"), None)
    lines += [
        "",
        "## Efficiency audit and Extension 2 — MBU-aware right-sizing",
        "",
    ]
    if lie:
        lines.append(
            f"`gpu-h100-4` reports **{lie['gpu_util_pct']:.1f}% GPU-Util** but only "
            f"**{lie['mfu']:.3f} MFU**. GPU-Util is a time-active clock: memory stalls, "
            "communication, launch overhead, or inefficient kernels can keep the device "
            "'busy' without retiring many FLOPs. The telemetry flags the symptom; a "
            "profiler is required before assigning one root cause."
        )
    lines += [
        "",
        "A replacement must fit peak observed memory with 10% headroom and provide at "
        "least 20% bandwidth headroom. This is why choosing only the cheapest $/GPU-hour "
        "would be unsafe.",
        "",
        "| GPU | Current → target | MBU | Required / target HBM | Required / target BW | $/GB before → after | Monthly saving |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    if r1["rightsize_recommendations"]:
        for row in r1["rightsize_recommendations"]:
            lines.append(
                f"| {row['gpu_id']} | {row['current_gpu']} → {row['recommended_gpu']} | "
                f"{row['mbu']:.3f} | {row['required_hbm_gb']:.1f} / {row['target_hbm_gb']:.0f} GB | "
                f"{row['required_bw_tbs']:.3f} / {row['target_bw_tbs']:.2f} TB/s | "
                f"${row['current_usd_per_gb']:.4f} → ${row['target_usd_per_gb']:.4f} | "
                f"${row['monthly_savings']:,.0f} |"
            )
    else:
        lines.append("| — | No safe cheaper candidate | — | — | — | — | $0 |")

    lines += [
        "",
        "## Extension 3 — Cache economics",
        "",
        "Cache savings are counted only when observed repeat reads exceed write, read, "
        "and TTL-storage break-even.",
        "",
        "| Tier | Write cost | Read multiplier | Storage | Break-even reads | Observed reads | Decision |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for tier, row in r2["cache_analysis"].items():
        lines.append(
            f"| {tier} | {row['write_cost']:.2f}x | {row['read_discount']:.2f}x | "
            f"{row['storage_cost']:.2f}x | {row['break_even_reads']} | "
            f"{row['avg_reads']:.2f} | {'cache' if row['worth_it'] else 'do not cache'} |"
        )

    reasoning = r2["reasoning"]
    lines += [
        "",
        "## Extension 4 — Reasoning budget",
        "",
        "| Signal | Reasoning share / value |",
        "|---|---:|",
        f"| Requests | {reasoning['request_share_pct']:.1f}% |",
        f"| Tokens | {reasoning['token_share_pct']:.1f}% |",
        f"| Optimized inference cost | {reasoning['cost_share_pct']:.1f}% ({_money(reasoning['reasoning_cost_usd'])}/day) |",
        f"| Energy | {reasoning['energy_share_pct']:.1f}% ({reasoning['reasoning_energy_wh']:,.0f} Wh/day) |",
        (
            f"| 5% cap counterfactual | save {_money(reasoning['cap_savings_usd'])}/day and "
            f"{reasoning['cap_savings_wh']:,.0f} Wh/day |"
        ),
        "",
        f"Routing rule: **{reasoning['routing_rule']}** The estimate reroutes the excess "
        "to standard inference and is deliberately not included in the committed savings "
        "waterfall until quality is validated.",
        "",
        "## Cost allocation",
        "",
        f"Tag coverage is **{r4['tag_coverage']:.1%}**; the 80% gate is therefore "
        f"**{'open' if r4['chargeback_ready'] else 'closed'}** for chargeback.",
        "",
        "| Team | Daily attributed spend |",
        "|---|---:|",
    ]
    for team, cost in sorted(r4["by_team"].items(), key=lambda item: -item[1]):
        lines.append(f"| {team} | ${cost:,.2f} |")

    carbon = r3["carbon_scheduling"]
    lines += [
        "",
        "## Extension 5 — Carbon-aware scheduling",
        "",
        (
            f"The {carbon['jobs_considered']} interruptible jobs consume "
            f"{carbon['energy_kwh']:,.1f} kWh in the simulated month."
        ),
        "",
        "| Region | $/kWh | gCO2/kWh | Electricity cost | Carbon |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in carbon["regions"]:
        lines.append(
            f"| {row['region']} | ${row['usd_per_kwh']:.3f} | {row['gco2_per_kwh']:.0f} | "
            f"${row['energy_cost_usd']:,.2f} | {row['carbon_kg']:,.2f} kgCO2e |"
        )
    lines += [
        "",
        f"- Cheapest: **{carbon['cheapest_region']}**",
        f"- Cleanest: **{carbon['cleanest_region']}**",
        f"- Balanced cost/carbon score: **{carbon['balanced_region']}**",
        (
            f"- Moving eligible jobs from `us-east-1` to `{carbon['cleanest_region']}` "
            f"saves **{carbon['carbon_saved_kg']:,.1f} kgCO2e ({carbon['carbon_saved_pct']:.1f}%)**."
        ),
        f"- Latency trade-off: {carbon['latency_note']}",
        "",
        "## Prioritized action plan",
        "",
        "1. **Stop idle capacity and enforce model routing/cache gates** — low migration risk, immediate measurement in $/1M-token.",
        "2. **Apply the spot/reserved matrix** — checkpoint finite training jobs; reserve only stable inference after term break-even.",
        "3. **Canary the A10G → L4 right-size changes** — verify latency/SLO and memory headroom before fleet rollout.",
        "4. **Enforce the reasoning budget after quality evaluation** — alert at 4% and hard-cap at 5% except approved overrides.",
        "5. **Schedule checkpointable jobs in cleaner regions** — choose Europe North for carbon or US East (WA) for balanced cost/carbon; keep interactive traffic near users.",
        "",
        "## Scope and assumptions",
        "",
        "Figures use deterministic synthetic telemetry and the June-2026 catalog snapshot. "
        "Savings buckets are applied to the baseline as an educational portfolio and may "
        "overlap operationally; production rollout should re-baseline after each lever, "
        "validate SLO/model quality, and refresh prices and grid intensity.",
    ]
    return "\n".join(lines)


def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)
    r4 = m4_allocation.run(verbose=False)

    inference_savings = (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]
    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = r1["rightsize_monthly_savings"]
    levers = {
        "Inference (cascade/cache/batch)": round(inference_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "MBU-aware right-sizing": round(rightsize_savings),
        "Kill idle GPUs": round(idle_savings),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    median_tokens = 800
    wh = sustainability.wh_per_query(median_tokens)
    carbon_schedule = r3["carbon_scheduling"]
    sustainability_snapshot = {
        "wh_per_query": wh,
        "carbon_g": sustainability.carbon_g(wh, "us-east-1"),
        "best_region": carbon_schedule["balanced_region"],
    }
    markdown = report.build_report(
        baseline,
        optimized,
        levers,
        sustainability=sustainability_snapshot,
    )
    markdown = markdown.replace(
        "# NimbusAI — GPU Cost Optimization Report",
        (
            "# NimbusAI — GPU Cost Optimization Report\n\n"
            f"**Student:** {STUDENT_NAME}\n\n**Student ID:** {STUDENT_ID}"
        ),
        1,
    )
    markdown += "\n" + _details_markdown(r1, r2, r3, r4)

    os.makedirs(os.path.join(ROOT, "outputs"), exist_ok=True)
    output_markdown = os.path.join(ROOT, "outputs", "report.md")
    with open(output_markdown, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown + "\n")
    png = report.savings_waterfall(
        levers,
        os.path.join(ROOT, "outputs", "savings.png"),
        baseline_usd=baseline,
    )

    extension_results = {
        "student": {"name": STUDENT_NAME, "id": STUDENT_ID},
        "extension_1_purchasing": {
            "simple_savings_pct": r3["simple_savings_pct"],
            "enhanced_savings_pct": r3["savings_pct"],
            "improvement_usd": r3["policy_improvement_usd"],
            "improvement_percentage_points": r3["policy_improvement_pp"],
            "recommendations": r3["recommendations"],
        },
        "extension_2_rightsizing": {
            "monthly_savings_usd": r1["rightsize_monthly_savings"],
            "recommendations": r1["rightsize_recommendations"],
        },
        "extension_3_cache": r2["cache_analysis"],
        "extension_4_reasoning": r2["reasoning"],
        "extension_5_carbon": carbon_schedule,
    }
    with open(
        os.path.join(ROOT, "outputs", "extension_results.json"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        json.dump(extension_results, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    if verbose:
        print("== M5 Optimization Report ==")
        print(markdown)
        chart_status = " + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"
        print(f"\nWritten: outputs/report.md + outputs/extension_results.json{chart_status}")

    return {
        "baseline_monthly": round(baseline),
        "optimized_monthly": round(optimized),
        "baseline_per_m": r2["baseline_per_m"],
        "optimized_per_m": r2["optimized_per_m"],
        "levers": levers,
        "total_savings_pct": round(total_pct, 1),
        "extensions_completed": 5,
    }


if __name__ == "__main__":
    run()
