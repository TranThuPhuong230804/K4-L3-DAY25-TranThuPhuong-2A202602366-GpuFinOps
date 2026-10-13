# Bonus — Prometheus + Grafana cost dashboard

The real observability stack (deck §10), wired to the lab's synthetic telemetry. A
tiny stdlib exporter turns telemetry into GPU **cost** metrics — including
`gpu_wasted_cost_usd_per_hr = (1 - MFU) * $/hr`, i.e. the money you pay for FLOPs you
don't use.

```bash
# from this folder:
docker compose up                       # Grafana: http://localhost:3000 (admin/admin)
#                                         Prometheus: http://localhost:9090
```

No Docker? The exporter is pure-Python:

```bash
python exporter.py                      # then: curl http://localhost:9101/metrics
```

Open the **"GPU Cost & Efficiency"** dashboard and compare *GPU-Util %* vs *MFU* — the
util-lie GPUs jump out, and the wasted-\$/hr panel ranks them by money leaked.

The exporter also publishes average board power and estimated `gCO2e/hour`. The
dashboard contains five validated panels; `python bonus/run_all.py` exports a
scrape snapshot to `outputs/bonus_prometheus_metrics.txt` without requiring Docker.
