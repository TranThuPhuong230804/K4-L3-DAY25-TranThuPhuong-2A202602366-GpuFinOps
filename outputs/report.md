# NimbusAI — GPU Cost Optimization Report

**Student:** Trần Thu Phương

**Student ID:** 2A202602366

- **Period:** monthly
- **Baseline spend:** $18,005
- **Optimized spend:** $9,209
- **Projected savings:** $8,796 (**49%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,208 |
| Purchasing (spot/reserved) | $6,700 |
| MBU-aware right-sizing | $288 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Recommended balanced region: us-east-wa

_Figures are June-2026 as-of snapshots; re-baseline before acting._

## Unit economics

| Metric | Baseline | Optimized | Change |
|---|---:|---:|---:|
| Inference cost / 1M tokens | $6.488 | $1.142 | -82.4% |
| Daily inference spend | $48.87 | $8.60 | -$40.27 |

The unit metric is the decision metric: a lower hourly GPU price is not an optimization if throughput falls enough to increase $/1M-token.

## Extension 1 — Risk- and term-aware purchasing

The original duty-cycle-only policy saves **40.5%**; the enhanced policy saves **40.5%** after GPU-specific interruption/rework and 1-year-versus-3-year commitment costs. Although both round to the same tenth of a percent, the enhanced policy is **$9.52/month better (+0.058 percentage points)**.

| Workload | GPU | Tier | Commitment | Interrupt risk | On-demand | Optimized |
|---|---|---|---:|---:|---:|---:|
| job-train-llm | H100 | spot | none | 4.0% | $5,600 | $3,528 |
| job-train-embed | A100 | spot | none | 8.0% | $358 | $235 |
| job-finetune | H100 | spot | none | 4.0% | $90 | $57 |
| job-infer-chat | A10G | reserved | 3yr | 12.0% | $4,320 | $2,592 |
| job-infer-rag | A100 | reserved | 3yr | 8.0% | $3,866 | $2,160 |
| job-infer-search | L4 | reserved | 3yr | 10.0% | $1,728 | $972 |
| job-dev-sandbox | A10G | spot | none | 12.0% | $352 | $153 |
| job-batch-eval | H100 | spot | none | 4.0% | $225 | $142 |

## Efficiency audit and Extension 2 — MBU-aware right-sizing

`gpu-h100-4` reports **98.2% GPU-Util** but only **0.194 MFU**. GPU-Util is a time-active clock: memory stalls, communication, launch overhead, or inefficient kernels can keep the device 'busy' without retiring many FLOPs. The telemetry flags the symptom; a profiler is required before assigning one root cause.

A replacement must fit peak observed memory with 10% headroom and provide at least 20% bandwidth headroom. This is why choosing only the cheapest $/GPU-hour would be unsafe.

| GPU | Current → target | MBU | Required / target HBM | Required / target BW | $/GB before → after | Monthly saving |
|---|---|---:|---:|---:|---:|---:|
| gpu-a10g-0 | A10G → L4 | 0.235 | 22.3 / 24 GB | 0.169 / 0.30 TB/s | $0.0417 → $0.0333 | $144 |
| gpu-a10g-1 | A10G → L4 | 0.302 | 22.4 / 24 GB | 0.217 / 0.30 TB/s | $0.0417 → $0.0333 | $144 |

## Extension 3 — Cache economics

Cache savings are counted only when observed repeat reads exceed write, read, and TTL-storage break-even.

| Tier | Write cost | Read multiplier | Storage | Break-even reads | Observed reads | Decision |
|---|---:|---:|---:|---:|---:|---|
| small | 1.20x | 0.10x | 0.02x | 1 | 10.32 | cache |
| large | 1.25x | 0.10x | 0.05x | 1 | 2.89 | cache |

## Extension 4 — Reasoning budget

| Signal | Reasoning share / value |
|---|---:|
| Requests | 8.4% |
| Tokens | 16.5% |
| Optimized inference cost | 16.3% ($1.40/day) |
| Energy | 94.0% (29,788 Wh/day) |
| 5% cap counterfactual | save $0.41/day and 11,932 Wh/day |

Routing rule: **Use reasoning only for complexity_score >= 0.80 and cap it at 5% of requests.** The estimate reroutes the excess to standard inference and is deliberately not included in the committed savings waterfall until quality is validated.

## Cost allocation

Tag coverage is **91.8%**; the 80% gate is therefore **open** for chargeback.

| Team | Daily attributed spend |
|---|---:|
| assistant | $2.66 |
| search | $2.50 |
| eval | $1.80 |
| rag | $1.65 |

## Extension 5 — Carbon-aware scheduling

The 5 interruptible jobs consume 1,789.0 kWh in the simulated month.

| Region | $/kWh | gCO2/kWh | Electricity cost | Carbon |
|---|---:|---:|---:|---:|
| us-east-1 | $0.120 | 380 | $214.68 | 679.82 kgCO2e |
| us-west-2 | $0.070 | 120 | $125.23 | 214.68 kgCO2e |
| europe-north1 | $0.090 | 30 | $161.01 | 53.67 kgCO2e |
| europe-central2 | $0.180 | 660 | $322.02 | 1,180.74 kgCO2e |
| us-east-wa | $0.055 | 90 | $98.39 | 161.01 kgCO2e |

- Cheapest: **us-east-wa**
- Cleanest: **europe-north1**
- Balanced cost/carbon score: **us-east-wa**
- Moving eligible jobs from `us-east-1` to `europe-north1` saves **626.1 kgCO2e (92.1%)**.
- Latency trade-off: The cleanest region may be farther from users; move checkpointable batch/training jobs, but keep latency-sensitive inference near demand.

## Prioritized action plan

1. **Stop idle capacity and enforce model routing/cache gates** — low migration risk, immediate measurement in $/1M-token.
2. **Apply the spot/reserved matrix** — checkpoint finite training jobs; reserve only stable inference after term break-even.
3. **Canary the A10G → L4 right-size changes** — verify latency/SLO and memory headroom before fleet rollout.
4. **Enforce the reasoning budget after quality evaluation** — alert at 4% and hard-cap at 5% except approved overrides.
5. **Schedule checkpointable jobs in cleaner regions** — choose Europe North for carbon or US East (WA) for balanced cost/carbon; keep interactive traffic near users.

## Scope and assumptions

Figures use deterministic synthetic telemetry and the June-2026 catalog snapshot. Savings buckets are applied to the baseline as an educational portfolio and may overlap operationally; production rollout should re-baseline after each lever, validate SLO/model quality, and refresh prices and grid intensity.
