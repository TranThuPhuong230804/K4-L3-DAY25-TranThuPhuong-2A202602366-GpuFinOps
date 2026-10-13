# Lab 25 — GPU FinOps Optimization Workshop

> **AICB · Phase 2 · Track 2 (Infrastructure) · Day 25** — pairs with the deck
> `day25-gpu-finops-cost-optimization.tex`. Deliverable: a **baseline-vs-optimized
> GPU cost report** (Milestone 2 input).

You are the new **FinOps engineer** at *NimbusAI*, an LLM-product startup whose GPU
bill is out of control. You're handed realistic (synthetic) telemetry, a 2026 price
catalog, and token logs. Your job: **find the waste and cut the bill 40–95%** — and
prove it in `$/1M-token`, not `$/GPU-hr`.

Everything here runs on a **laptop with no GPU, no cloud account, and no API key.**

---

## Completed submission

**Student:** Trần Thu Phương

**Student ID:** 2A202602366

This submission implements all five **Your Turn** extensions and all three bonuses.
Measured evidence is generated in `outputs/report.md`, `outputs/extension_results.json`,
and `outputs/bonus_summary.md`.

```bash
python missions/run_all.py
python bonus/run_all.py
python verify.py
pytest -q
```

The final suite contains the original 15 grading tests plus 9 extension/bonus tests
(24 total).

---

## Why this lab is a *simulation*

Real GPU FinOps means real cloud billing, real spot markets, and real DCGM telemetry —
none of which 167 students can safely share. So the graded lab is **data-driven**: you
analyze realistic synthetic data with a small Python engine (`finops/`). The figures are
**June-2026 as-of snapshots aligned with the deck's RESEARCH dossier** (e.g. H100 ~\$2.5/hr
neocloud, batch −50% × cache −90% ≈ 95% off, reasoning ~74–86× energy). Optional bonuses
connect to the *real* stack (a LiteLLM-style tracker, a local model, Prometheus+Grafana).

---

## Setup

```bash
cd Day25-Track2-GPU-FinOps-Lab
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python verify.py            # should print 11/11 checks passed
```

Quick run of everything:

```bash
python data/generate.py         # (re)generate the synthetic data (deterministic, seed=25)
python missions/run_all.py      # run M1..M5 and print results
pytest -q                       # 15 unit + integration tests
```

Outputs land in `outputs/` (`report.md`, `savings.png`, `focus_export.csv`).

---

## The engine — `finops/`

| Module | What it gives you |
|---|---|
| `metrics.py` | `compute_mfu`, `compute_mbu`, `roofline_regime`, `flag_util_lies`, `idle_waste_usd` |
| `pricing.py` | `request_cost`, `dollars_per_million`, `discount_stack`, `break_even_utilization`, `recommend_tier`, `spot_checkpoint_cost` |
| `allocation.py` | `cost_by_tag`, `tag_coverage`, `chargeback_ready`, `to_focus_rows` |
| `sustainability.py` | `wh_per_query`, `carbon_g`, `energy_cost_usd`, `tokens_per_watt` |
| `report.py` | `build_report`, `savings_waterfall` |

---

## The 5 missions

| # | Mission | You learn (deck §) | Run |
|---|---|---|---|
| **M1** | **Efficiency Audit** — MFU/MBU, the *GPU-Util lie*, idle waste | §5 | `python missions/m1_efficiency_audit.py` |
| **M2** | **Inference Cost Levers** — `$/1M-token`, batch × cache × cascade | §7 | `python missions/m2_inference_levers.py` |
| **M3** | **Purchasing Strategy** — break-even, tier choice, spot checkpoint sim | §4 | `python missions/m3_purchasing.py` |
| **M4** | **Cost Allocation** — tags → showback → chargeback, FOCUS export | §10 | `python missions/m4_allocation.py` |
| **M5** | **Optimization Report** — baseline vs optimized + sustainability | §1/§11 | `python missions/m5_report.py` |

The headline lesson of **M1**: `gpu-h100-4` reads **98% GPU-Util but only ~0.20 MFU** —
you're paying the full H100-hour for a fifth of the FLOPs. `nvidia-smi` util is a "busy"
clock, not an efficiency metric.

---

## Data dictionary (`data/`)

| File | Rows | Key columns |
|---|---|---|
| `price_catalog.csv` | 7 GPUs | `on_demand_hr`, `spot_hr`, `reserved_3yr_hr`, `peak_tflops_fp16`, `peak_bw_tbs`, `watts` |
| `gpu_telemetry.csv` | 11 GPUs × 24h | `gpu_util_pct`, `achieved_tflops`, `achieved_bw_tbs`, `power_w` |
| `token_usage.csv` | 2,400 reqs | `route_tier`, `input/output/cached_input_tokens`, `is_batch`, `is_reasoning`, `team`, `project` |
| `workloads.csv` | 8 jobs | `hours_per_day`, `days`, `interruptible`, `gpu_type`, `num_gpus` |

`data/generate.py` is seeded — regenerating always yields identical data.

---

## Your Turn (extensions — where the real learning is)

These are intentionally left for you. The lab passes without them; do them to go deeper.

1. **Better tier policy.** `pricing.recommend_tier()` uses a deliberately simple duty-cycle
   rule. Rewrite it to also weigh interruption rate per GPU type and the 3yr-vs-1yr discount.
   Does total purchasing savings improve?
2. **MBU-aware right-sizing.** In M1, decide *which* GPU each memory-bound inference workload
   should move to using `$/GB-VRAM` and `peak_bw_tbs` — not just `$/GPU-hr`.
3. **Cache economics.** In M2, prompt caching only pays above a read threshold (and Gemini
   charges storage). Add a `cache_is_worth_it()` check before counting cache savings.
4. **Reasoning budget.** Quantify the extra `$` and `Wh` the `is_reasoning` traffic costs in
   M2/M5, and propose a routing rule that caps it.
5. **Carbon-aware scheduling.** Use `sustainability` to move the interruptible training jobs
   to the cheapest+cleanest region-hour and report the carbon saved.

---

## Deliverable & grading

Submit `outputs/report.md` (+ `savings.png`) plus a short write-up:

| Component | Weight |
|---|---|
| `verify.py` passes 11/11 | 30% |
| `pytest` passes | 20% |
| Report shows baseline vs optimized in **$/1M-token** with per-lever savings | 30% |
| ≥2 "Your Turn" extensions implemented + measured | 20% |

This is the **Milestone 2** FinOps input — bring the report to the platform demo.

---

## Bonuses (optional, ungraded — lab passes without them)

- **`bonus/litellm_tracker/`** — a LiteLLM-style token-cost proxy with per-API-key **budget
  caps** (mock backend; no key needed). Real `$/request` attribution, the §10 token tier.
- **`bonus/local_model/`** — run a tiny model on CPU to measure **real tok/s** and compare
  real `$/token` to the simulation. Skips gracefully if deps/model are absent.
- **`bonus/docker/`** — `docker-compose` with **Prometheus + Grafana** and a tiny exporter
  publishing the synthetic GPU cost/util metrics, plus a prebuilt cost dashboard.

---

## Notes

- **Prices move monthly.** Every dollar figure is a June-2026 snapshot; re-baseline before
  acting. The *structural* lessons (measure $/token, MFU not GPU-Util, stack discounts,
  break-even before reserving, tag before chargeback) are durable.
- Pure-Python graded path: `pandas`, `matplotlib`, `pytest`. No GPU / key / Docker required.
