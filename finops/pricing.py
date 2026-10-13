"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations

import math


# Illustrative hourly pre-emption probabilities. Keep the assumption beside
# the purchasing policy so it is visible and easy to re-baseline.
GPU_INTERRUPTION_RATES = {
    "H100": 0.04,
    "H200": 0.06,
    "A100": 0.08,
    "A10G": 0.12,
    "L4": 0.10,
    "B200": 0.07,
    "MI300X": 0.09,
}


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


def recommend_tier(
    hours_per_day: float,
    interruptible: bool,
    reserved_discount: float = 0.45,
    *,
    gpu_type: str | None = None,
    on_demand_hr: float | None = None,
    spot_hr: float | None = None,
    interruption_rate: float | None = None,
    checkpoint_overhead_frac: float = 0.03,
    rework_hours_per_interrupt: float = 0.5,
) -> str:
    """Pick a purchasing tier using duty cycle and risk-adjusted spot cost.

    With catalog inputs, the policy includes the GPU-specific interruption and
    checkpoint/rework cost before selecting spot. The three-argument form stays
    backward-compatible with the lab's original documented policy.
    """
    duty = max(0.0, hours_per_day) / 24.0
    be = break_even_utilization(reserved_discount)
    if interruptible and hours_per_day < 24:
        rate = interruption_rate
        if rate is None:
            rate = GPU_INTERRUPTION_RATES.get(gpu_type or "", 0.05)
        if on_demand_hr is not None and spot_hr is not None:
            effective_spot = spot_hr * (
                1.0 + checkpoint_overhead_frac
                + max(0.0, rate) * rework_hours_per_interrupt
            )
            if effective_spot >= on_demand_hr:
                return "on_demand"
        return "spot"
    if duty >= be:
        return "reserved"
    return "on_demand"


def select_reserved_term(
    expected_duration_days: float,
    on_demand_hr: float,
    reserved_1yr_hr: float,
    reserved_3yr_hr: float,
) -> dict:
    """Choose the cheapest commitment including each term's minimum duration.

    A commitment is paid for its full one- or three-year term even when the
    workload ends sooner. This avoids comparing hourly discounts while ignoring
    stranded commitment months.
    """
    duration = max(0.0, expected_duration_days)
    candidates = {
        "on_demand": duration * 24.0 * max(0.0, on_demand_hr),
        "1yr": max(duration, 365.0) * 24.0 * max(0.0, reserved_1yr_hr),
        "3yr": max(duration, 1095.0) * 24.0 * max(0.0, reserved_3yr_hr),
    }
    term = min(candidates, key=candidates.get)
    rates = {
        "on_demand": on_demand_hr,
        "1yr": reserved_1yr_hr,
        "3yr": reserved_3yr_hr,
    }
    return {
        "term": term,
        "hourly_rate": round(max(0.0, rates[term]), 4),
        "planning_cost": round(candidates[term], 2),
        "candidate_costs": {k: round(v, 2) for k, v in candidates.items()},
    }


def cache_break_even_reads(
    write_cost: float = 1.25,
    read_discount: float = 0.10,
    storage_cost: float = 0.0,
) -> int | float:
    """Minimum repeated reads after one write needed for caching to pay.

    Costs are normalized to an ordinary input-token read. Without caching, one
    write plus *r* repeats costs ``1 + r``. With caching it costs
    ``write_cost + storage_cost + r * read_discount``.
    """
    write_cost = max(0.0, write_cost)
    storage_cost = max(0.0, storage_cost)
    if read_discount >= 1.0:
        return 0 if write_cost + storage_cost < 1.0 else math.inf
    read_discount = max(0.0, read_discount)
    raw = (write_cost + storage_cost - 1.0) / (1.0 - read_discount)
    # Profit requires a strict inequality, so exact break-even needs one more read.
    return max(0, math.floor(raw) + 1)


def cache_is_worth_it(
    avg_reads: float,
    write_cost: float = 1.25,
    read_discount: float = 0.10,
    storage_cost: float = 0.0,
) -> bool:
    """Return whether observed repeat reads clear the cache break-even point."""
    return max(0.0, avg_reads) >= cache_break_even_reads(
        write_cost=write_cost,
        read_discount=read_discount,
        storage_cost=storage_cost,
    )


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }
