"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations

import os
import tempfile


def build_report(baseline_usd: float, optimized_usd: float, levers: dict,
                 sustainability: dict | None = None, period: str = "monthly") -> str:
    """Return a markdown cost-optimization report."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"- **Period:** {period}",
        f"- **Baseline spend:** ${baseline_usd:,.0f}",
        f"- **Optimized spend:** ${optimized_usd:,.0f}",
        f"- **Projected savings:** ${savings:,.0f} (**{pct:.0f}%**)",
        "",
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")
    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Recommended balanced region: {sustainability.get('best_region', 'n/a')}",
        ]
    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str, baseline_usd: float | None = None) -> str:
    """Write a baseline-to-optimized waterfall PNG and return its path."""
    try:
        # Keep matplotlib's font cache in a writable temp location on locked-down
        # lab machines instead of relying on the user's home directory.
        os.environ.setdefault(
            "MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "lab25-matplotlib"),
        )
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    lever_names = list(levers)
    savings = [max(0.0, float(levers[name])) for name in lever_names]
    baseline = float(baseline_usd) if baseline_usd is not None else sum(savings)
    running = baseline
    bottoms = [0.0]
    heights = [baseline]
    for amount in savings:
        running -= amount
        bottoms.append(running)
        heights.append(amount)
    optimized = max(0.0, running)
    bottoms.append(0.0)
    heights.append(optimized)

    labels = ["Baseline"] + [name.replace(" (", "\n(") for name in lever_names] + ["Optimized"]
    colors = ["#355f91"] + ["#dc7c32"] * len(savings) + ["#3b8f65"]
    positions = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(11, 5.5))
    bars = ax.bar(positions, heights, bottom=bottoms, color=colors, width=0.72)

    # Connect the ending level of each bar to the next one.
    levels = [baseline]
    level = baseline
    for amount in savings:
        level -= amount
        levels.append(level)
    for index, level in enumerate(levels[:-1]):
        ax.plot([index + 0.36, index + 0.64], [level, level], color="#777777", linewidth=1)

    ax.bar_label(bars, labels=[f"${height:,.0f}" for height in heights], padding=3, fontsize=9)
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Monthly GPU spend (USD)")
    ax.set_title("GPU cost optimization waterfall")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    ax.margins(y=0.12)
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
