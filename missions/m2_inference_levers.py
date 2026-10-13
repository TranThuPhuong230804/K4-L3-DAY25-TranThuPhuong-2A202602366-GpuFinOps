"""M2 - Inference cost levers plus cache and reasoning-budget extensions.

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations

import os as _os
import sys as _sys
from collections import defaultdict

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from finops import pricing, sustainability
from missions._common import load_csv, num

# $/1M tokens (input, output), illustrative June-2026 snapshot.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}

# Normalized cache economics per model tier. Storage is expressed as an
# equivalent fraction of an ordinary input-token charge for the cache TTL.
CACHE_POLICIES = {
    "small": {"write_cost": 1.20, "read_discount": 0.10, "storage_cost": 0.02},
    "large": {"write_cost": 1.25, "read_discount": 0.10, "storage_cost": 0.05},
}
REASONING_REQUEST_CAP = 0.05


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")

    # Approximate a cache entry by hour + owning workload + model tier. Repeats
    # within the hour are reads of the same shared prompt/cache entry.
    cache_groups = {tier: defaultdict(int) for tier in MODEL_PRICES}
    for r in rows:
        if int(num(r["cached_input_tokens"])) <= 0:
            continue
        cache_key = (r["ts"][:13], r["team"], r["project"], r["route_tier"])
        cache_groups[r["route_tier"]][cache_key] += 1

    cache_analysis = {}
    for tier, groups in cache_groups.items():
        repeat_reads = [max(0, count - 1) for count in groups.values()]
        avg_reads = sum(repeat_reads) / len(repeat_reads) if repeat_reads else 0.0
        policy = CACHE_POLICIES[tier]
        threshold = pricing.cache_break_even_reads(**policy)
        cache_analysis[tier] = {
            "avg_reads": round(avg_reads, 2),
            "break_even_reads": threshold,
            "worth_it": pricing.cache_is_worth_it(avg_reads=avg_reads, **policy),
            **policy,
        }

    base_cost = cascade_cost = cache_cost = opt_cost = 0.0
    total_tokens = 0
    reasoning = {
        "requests": 0,
        "tokens": 0,
        "cost_usd": 0.0,
        "energy_wh": 0.0,
        "counterfactual_cost_savings": 0.0,
        "counterfactual_energy_savings_wh": 0.0,
    }
    ordinary = {"requests": 0, "tokens": 0, "cost_usd": 0.0, "energy_wh": 0.0}

    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        is_reasoning = bool(int(num(r["is_reasoning"])))
        total_tokens += inp + out

        # Baseline: everything on the large model, no cache and no batch.
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)

        # Apply levers sequentially so each saving is measurable and additive.
        tier = r["route_tier"]
        pin, pout = MODEL_PRICES[tier]
        cascade_row = pricing.request_cost(inp, out, pin, pout)
        cascade_cost += cascade_row

        cache_enabled = cache_analysis[tier]["worth_it"]
        applied_cached = cached if cache_enabled else 0
        cached_row = pricing.request_cost(inp, out, pin, pout, cached_in=applied_cached)

        # Amortize cache-write premium and TTL storage across observed repeats.
        cache_overhead = 0.0
        if applied_cached:
            cp = CACHE_POLICIES[tier]
            repeats = max(1.0, cache_analysis[tier]["avg_reads"])
            cache_overhead = (
                applied_cached
                / 1e6
                * pin
                * (max(0.0, cp["write_cost"] - 1.0) + cp["storage_cost"])
                / repeats
            )
        cached_row += cache_overhead
        cache_cost += cached_row

        optimized_row = pricing.request_cost(
            inp,
            out,
            pin,
            pout,
            cached_in=applied_cached,
            batch=is_batch,
        ) + cache_overhead
        opt_cost += optimized_row

        bucket = reasoning if is_reasoning else ordinary
        bucket["requests"] += 1
        bucket["tokens"] += inp + out
        bucket["cost_usd"] += optimized_row
        bucket["energy_wh"] += sustainability.wh_per_query(
            inp + out, is_reasoning=is_reasoning,
        )

        if is_reasoning:
            # Data generation models reasoning as roughly 6x output tokens.
            normal_out = max(1, round(out / 6))
            normal_cost = pricing.request_cost(
                inp,
                normal_out,
                pin,
                pout,
                cached_in=applied_cached,
                batch=is_batch,
            ) + cache_overhead
            normal_wh = sustainability.wh_per_query(inp + normal_out, is_reasoning=False)
            reasoning["counterfactual_cost_savings"] += max(0.0, optimized_row - normal_cost)
            reasoning["counterfactual_energy_savings_wh"] += max(
                0.0,
                sustainability.wh_per_query(inp + out, is_reasoning=True) - normal_wh,
            )

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0
    lever_savings = {
        "model_cascade": base_cost - cascade_cost,
        "prompt_cache": cascade_cost - cache_cost,
        "batch_api": cache_cost - opt_cost,
    }

    current_reasoning_share = reasoning["requests"] / len(rows) if rows else 0.0
    keep_fraction = (
        min(1.0, REASONING_REQUEST_CAP / current_reasoning_share)
        if current_reasoning_share
        else 1.0
    )
    reroute_fraction = 1.0 - keep_fraction
    cap_savings_usd = reasoning["counterfactual_cost_savings"] * reroute_fraction
    cap_savings_wh = reasoning["counterfactual_energy_savings_wh"] * reroute_fraction
    all_energy = reasoning["energy_wh"] + ordinary["energy_wh"]
    reasoning_summary = {
        "request_share_pct": round(current_reasoning_share * 100, 1),
        "token_share_pct": round(reasoning["tokens"] / total_tokens * 100, 1) if total_tokens else 0.0,
        "cost_share_pct": round(reasoning["cost_usd"] / opt_cost * 100, 1) if opt_cost else 0.0,
        "energy_share_pct": round(reasoning["energy_wh"] / all_energy * 100, 1) if all_energy else 0.0,
        "reasoning_cost_usd": round(reasoning["cost_usd"], 2),
        "ordinary_cost_usd": round(ordinary["cost_usd"], 2),
        "reasoning_energy_wh": round(reasoning["energy_wh"], 2),
        "ordinary_energy_wh": round(ordinary["energy_wh"], 2),
        "cap_request_share_pct": REASONING_REQUEST_CAP * 100,
        "cap_savings_usd": round(cap_savings_usd, 2),
        "cap_savings_wh": round(cap_savings_wh, 2),
        "routing_rule": (
            "Use reasoning only for complexity_score >= 0.80 and cap it at 5% of requests."
        ),
    }

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(
            "discount stack (batch + 100% cache): "
            f"{pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive"
        )
        print("\ncache economics:")
        for tier, analysis in cache_analysis.items():
            decision = "CACHE" if analysis["worth_it"] else "DO NOT CACHE"
            print(
                f"  {tier:5} observed={analysis['avg_reads']:.1f} reads/entry  "
                f"break-even={analysis['break_even_reads']}  -> {decision}"
            )
        print("\nreasoning budget:")
        print(
            f"  {reasoning_summary['request_share_pct']:.1f}% of requests consumes "
            f"{reasoning_summary['cost_share_pct']:.1f}% of cost and "
            f"{reasoning_summary['energy_share_pct']:.1f}% of energy"
        )
        print(
            f"  cap at {reasoning_summary['cap_request_share_pct']:.0f}% -> save "
            f"${reasoning_summary['cap_savings_usd']:.2f}/day and "
            f"{reasoning_summary['cap_savings_wh']:,.0f} Wh/day"
        )

    return {
        "baseline_daily": round(base_cost, 2),
        "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3),
        "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1),
        "total_tokens": total_tokens,
        "lever_savings_daily": {k: round(v, 2) for k, v in lever_savings.items()},
        "cache_analysis": cache_analysis,
        "reasoning": reasoning_summary,
    }


if __name__ == "__main__":
    run()
