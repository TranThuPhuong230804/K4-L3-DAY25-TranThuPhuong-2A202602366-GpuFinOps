"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {
        "util": [], "mfu": [], "mbu": [], "bw": [], "memory": [],
        "type": None, "workload": None, "idle_hours": 0,
    })
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["workload"] = r["workload"]
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        a["bw"].append(num(r["achieved_bw_tbs"]))
        a["memory"].append(num(r["mem_used_gb"]))
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "achieved_bw_tbs": round(sum(a["bw"]) / len(a["bw"]), 3),
            "max_mem_used_gb": round(max(a["memory"]), 1),
            "workload": a["workload"],
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(cat[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # Extension 2: right-size memory-bound inference using both capacity and
    # bandwidth constraints. A cheap GPU that cannot hold the model or sustain
    # measured bandwidth is not a valid recommendation.
    gpu_economics = []
    for gtype, c in cat.items():
        hbm = num(c["hbm_gb"])
        hourly = num(c["on_demand_hr"])
        gpu_economics.append({
            "gpu_type": gtype,
            "hourly_usd": hourly,
            "hbm_gb": hbm,
            "peak_bw_tbs": num(c["peak_bw_tbs"]),
            "usd_per_gb_vram": round(hourly / hbm, 4) if hbm else 0.0,
        })

    rightsize = []
    for s in summary:
        if s["workload"] not in ("infer", "embed") or s["mbu"] >= 0.60:
            continue
        current = cat[s["gpu_type"]]
        current_price = num(current["on_demand_hr"])
        required_hbm = s["max_mem_used_gb"] * 1.10
        required_bw = s["achieved_bw_tbs"] * 1.20
        candidates = []
        for gtype, c in cat.items():
            price = num(c["on_demand_hr"])
            hbm = num(c["hbm_gb"])
            bw = num(c["peak_bw_tbs"])
            if hbm >= required_hbm and bw >= required_bw and price < current_price:
                candidates.append((price / hbm, price, -bw, gtype, c))
        if not candidates:
            continue
        _, target_price, _, target, target_cat = min(candidates)
        monthly_savings = (current_price - target_price) * 24 * 30
        rightsize.append({
            "gpu_id": s["gpu_id"],
            "current_gpu": s["gpu_type"],
            "recommended_gpu": target,
            "mbu": s["mbu"],
            "required_hbm_gb": round(required_hbm, 1),
            "required_bw_tbs": round(required_bw, 3),
            "target_hbm_gb": num(target_cat["hbm_gb"]),
            "target_bw_tbs": num(target_cat["peak_bw_tbs"]),
            "current_usd_per_gb": round(current_price / num(current["hbm_gb"]), 4),
            "target_usd_per_gb": round(target_price / num(target_cat["hbm_gb"]), 4),
            "monthly_savings": round(monthly_savings, 2),
            "savings_pct": round((1 - target_price / current_price) * 100, 1),
        })
    rightsize_monthly_savings = sum(r["monthly_savings"] for r in rightsize)

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")

        print("\nMBU-aware right-sizing (capacity + bandwidth constrained):")
        if rightsize:
            print(f"{'GPU':14}{'from':7}{'to':7}{'MBU':>7}{'$/GB before':>13}{'$/GB after':>12}{'save/mo':>11}")
            for r in rightsize:
                print(
                    f"{r['gpu_id']:14}{r['current_gpu']:7}{r['recommended_gpu']:7}"
                    f"{r['mbu']:>7.3f}{r['current_usd_per_gb']:>13.4f}"
                    f"{r['target_usd_per_gb']:>12.4f}${r['monthly_savings']:>10,.0f}"
                )
        else:
            print("  No cheaper GPU satisfies both HBM and bandwidth headroom.")
        print(f"Right-size savings: ${rightsize_monthly_savings:,.0f}/month")

    return {
        "summary": summary,
        "lies": lies,
        "idle_waste_daily": round(idle_waste, 2),
        "gpu_economics": sorted(gpu_economics, key=lambda x: x["usd_per_gb_vram"]),
        "rightsize_recommendations": rightsize,
        "rightsize_monthly_savings": round(rightsize_monthly_savings, 2),
    }


if __name__ == "__main__":
    run()
