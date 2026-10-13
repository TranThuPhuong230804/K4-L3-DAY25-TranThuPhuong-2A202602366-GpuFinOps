# Bonus completion evidence

**Student:** Trần Thu Phương

**Student ID:** 2A202602366

| Bonus | Measured evidence | Artifact |
|---|---|---|
| LiteLLM-style tracker | 15 accepted requests; budget guard triggered: True | `bonus_litellm_tracker.json` |
| Local CPU model | 1,210,047.3 tok/s; $0.000023/1M tokens | `bonus_local_model.json` |
| Prometheus + Grafana | 5 validated metrics and 5 dashboard panels | `bonus_prometheus_metrics.txt` |

The Docker stack is defined in `bonus/docker/docker-compose.yml`; the exporter path is also testable without Docker so grading remains offline-safe.
