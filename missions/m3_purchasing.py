"""M3 - Risk-aware purchasing and carbon-aware scheduling.

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from finops import pricing, sustainability
from missions._common import catalog_by_type, load_csv, num


def _simple_tier(hours_per_day: float, interruptible: bool) -> str:
    """Original lab policy, retained to measure the extension's impact."""
    if interruptible and hours_per_day < 24:
        return "spot"
    if hours_per_day / 24.0 >= pricing.break_even_utilization(0.45):
        return "reserved"
    return "on_demand"


def _tier_cost(tier: str, gpu_hours: float, catalog: dict, interruption_rate: float) -> float:
    on_demand = num(catalog["on_demand_hr"])
    if tier == "spot":
        return pricing.spot_checkpoint_cost(
            gpu_hours,
            num(catalog["spot_hr"]),
            on_demand,
            interrupt_rate=interruption_rate,
        )["spot_cost"]
    if tier == "reserved":
        return gpu_hours * num(catalog["reserved_3yr_hr"])
    return gpu_hours * on_demand


def _carbon_schedule(jobs: list[dict], catalog: dict) -> dict:
    """Compare all regions for the energy used by interruptible jobs."""
    energy_kwh = 0.0
    jobs_considered = 0
    for job in jobs:
        if not bool(int(num(job["interruptible"]))):
            continue
        jobs_considered += 1
        gpu_hours = num(job["hours_per_day"]) * num(job["days"]) * int(num(job["num_gpus"]))
        energy_kwh += gpu_hours * num(catalog[job["gpu_type"]]["watts"]) / 1000.0

    regions = []
    min_price, max_price = min(sustainability.REGION_PRICE_KWH.values()), max(sustainability.REGION_PRICE_KWH.values())
    min_carbon, max_carbon = min(sustainability.REGION_CARBON.values()), max(sustainability.REGION_CARBON.values())
    for region in sustainability.REGION_CARBON:
        price = sustainability.REGION_PRICE_KWH[region]
        intensity = sustainability.REGION_CARBON[region]
        price_norm = (price - min_price) / (max_price - min_price) if max_price > min_price else 0.0
        carbon_norm = (
            (intensity - min_carbon) / (max_carbon - min_carbon)
            if max_carbon > min_carbon
            else 0.0
        )
        regions.append({
            "region": region,
            "usd_per_kwh": price,
            "gco2_per_kwh": intensity,
            "energy_cost_usd": round(energy_kwh * price, 2),
            "carbon_kg": round(energy_kwh * intensity / 1000.0, 2),
            "balanced_score": round((price_norm + carbon_norm) / 2.0, 3),
        })

    cheapest = min(regions, key=lambda row: row["energy_cost_usd"])
    cleanest = min(regions, key=lambda row: row["carbon_kg"])
    balanced = min(regions, key=lambda row: row["balanced_score"])
    baseline = next(row for row in regions if row["region"] == "us-east-1")
    carbon_saved = baseline["carbon_kg"] - cleanest["carbon_kg"]
    return {
        "jobs_considered": jobs_considered,
        "energy_kwh": round(energy_kwh, 2),
        "regions": regions,
        "cheapest_region": cheapest["region"],
        "cleanest_region": cleanest["region"],
        "balanced_region": balanced["region"],
        "carbon_saved_kg": round(carbon_saved, 2),
        "carbon_saved_pct": round(carbon_saved / baseline["carbon_kg"] * 100, 1) if baseline["carbon_kg"] else 0.0,
        "latency_note": (
            "The cleanest region may be farther from users; move checkpointable batch/training jobs, "
            "but keep latency-sensitive inference near demand."
        ),
    }


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    catalog = catalog_by_type()
    on_demand_monthly = optimized_monthly = simple_policy_monthly = 0.0
    recommendations = []

    for job in jobs:
        gpu_type = job["gpu_type"]
        count = int(num(job["num_gpus"]))
        hours_per_day = num(job["hours_per_day"])
        active_days = num(job["days"])
        interruptible = bool(int(num(job["interruptible"])))
        gpu = catalog[gpu_type]
        gpu_hours = hours_per_day * active_days * count
        on_demand_rate = num(gpu["on_demand_hr"])
        on_demand_cost = gpu_hours * on_demand_rate
        interruption_rate = pricing.GPU_INTERRUPTION_RATES.get(gpu_type, 0.05)

        # Stable, non-interruptible inference is planned over a three-year
        # horizon; finite training/dev jobs use their explicit duration.
        stable_service = job["kind"] == "infer" and not interruptible and hours_per_day >= 18
        expected_duration_days = 1095 if stable_service else active_days
        term = pricing.select_reserved_term(
            expected_duration_days,
            on_demand_rate,
            num(gpu["reserved_1yr_hr"]),
            num(gpu["reserved_3yr_hr"]),
        )
        reserved_rate = term["hourly_rate"] if term["term"] != "on_demand" else on_demand_rate
        reserved_discount = 1.0 - reserved_rate / on_demand_rate if on_demand_rate else 0.0
        tier = pricing.recommend_tier(
            hours_per_day,
            interruptible,
            reserved_discount=reserved_discount,
            gpu_type=gpu_type,
            on_demand_hr=on_demand_rate,
            spot_hr=num(gpu["spot_hr"]),
            interruption_rate=interruption_rate,
        )
        if tier == "reserved" and term["term"] == "on_demand":
            tier = "on_demand"

        if tier == "spot":
            optimized_cost = pricing.spot_checkpoint_cost(
                gpu_hours,
                num(gpu["spot_hr"]),
                on_demand_rate,
                interrupt_rate=interruption_rate,
            )["spot_cost"]
            commitment = "none"
        elif tier == "reserved":
            optimized_cost = gpu_hours * reserved_rate
            commitment = term["term"]
        else:
            optimized_cost = on_demand_cost
            commitment = "none"

        simple_tier = _simple_tier(hours_per_day, interruptible)
        simple_cost = _tier_cost(simple_tier, gpu_hours, gpu, 0.05)
        on_demand_monthly += on_demand_cost
        optimized_monthly += optimized_cost
        simple_policy_monthly += simple_cost
        recommendations.append({
            "job_id": job["job_id"],
            "gpu_type": gpu_type,
            "tier": tier,
            "commitment": commitment,
            "interruption_rate_pct": round(interruption_rate * 100, 1),
            "expected_duration_days": expected_duration_days,
            "on_demand": round(on_demand_cost),
            "optimized": round(optimized_cost),
        })

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0
    simple_savings_pct = (
        (on_demand_monthly - simple_policy_monthly) / on_demand_monthly * 100
        if on_demand_monthly
        else 0.0
    )
    policy_improvement_usd = simple_policy_monthly - optimized_monthly
    policy_improvement_pp = savings_pct - simple_savings_pct

    # Extension evidence: GPU x duty-cycle x interruptibility decision matrix.
    policy_matrix = []
    for gpu_type, gpu in catalog.items():
        on_demand_rate = num(gpu["on_demand_hr"])
        reserved_discount = 1.0 - num(gpu["reserved_3yr_hr"]) / on_demand_rate
        for hours_per_day in (6, 18, 24):
            for interruptible in (False, True):
                policy_matrix.append({
                    "gpu_type": gpu_type,
                    "hours_per_day": hours_per_day,
                    "interruptible": interruptible,
                    "tier": pricing.recommend_tier(
                        hours_per_day,
                        interruptible,
                        reserved_discount=reserved_discount,
                        gpu_type=gpu_type,
                        on_demand_hr=on_demand_rate,
                        spot_hr=num(gpu["spot_hr"]),
                    ),
                })

    carbon = _carbon_schedule(jobs, catalog)

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'term':7}{'risk':>7}{'on-demand':>12}{'optimized':>12}")
        for row in recommendations:
            print(
                f"{row['job_id']:18}{row['gpu_type']:7}{row['tier']:11}{row['commitment']:7}"
                f"{row['interruption_rate_pct']:>6.1f}%${row['on_demand']:>11,}${row['optimized']:>11,}"
            )
        print(
            f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized "
            f"${optimized_monthly:,.0f} ({savings_pct:.1f}% saved)"
        )
        print(
            f"policy comparison: simple={simple_savings_pct:.1f}% saved, "
            f"risk+term aware={savings_pct:.1f}% saved "
            f"(${policy_improvement_usd:,.2f}/month better, {policy_improvement_pp:+.3f} pp)"
        )
        print("\ncarbon-aware scheduling for interruptible jobs:")
        print(f"{'region':18}{'$/kWh':>8}{'gCO2/kWh':>11}{'energy $':>11}{'carbon kg':>12}")
        for row in carbon["regions"]:
            print(
                f"{row['region']:18}{row['usd_per_kwh']:>8.3f}{row['gco2_per_kwh']:>11}"
                f"${row['energy_cost_usd']:>10,.2f}{row['carbon_kg']:>12,.2f}"
            )
        print(
            f"cleanest={carbon['cleanest_region']}, cheapest={carbon['cheapest_region']}, "
            f"balanced={carbon['balanced_region']}; save {carbon['carbon_saved_kg']:,.1f} kgCO2e "
            f"({carbon['carbon_saved_pct']:.1f}%)"
        )

    return {
        "recommendations": recommendations,
        "policy_matrix": policy_matrix,
        "on_demand_monthly": round(on_demand_monthly),
        "optimized_monthly": round(optimized_monthly),
        "simple_policy_monthly": round(simple_policy_monthly),
        "simple_savings_pct": round(simple_savings_pct, 1),
        "policy_improvement_usd": round(policy_improvement_usd, 2),
        "policy_improvement_pp": round(policy_improvement_pp, 3),
        "savings_pct": round(savings_pct, 1),
        "carbon_scheduling": carbon,
    }


if __name__ == "__main__":
    run()
