# Bonus — LiteLLM-style token-cost tracker

A ~60-line proxy that logs token usage, computes **$/request per API key**, and
**hard-stops** requests that would exceed a budget — the token-tier of cost
observability (deck §10). Mock backend, no key required.

```bash
cd bonus/litellm_tracker
python demo.py
```

You'll see `team-chat` blocked once it hits its \$0.05 cap, while `team-eval`
(small model + batch) stays cheap. To use a real provider, replace the `# MOCK
response` block in `tracker.py` with a real `litellm.completion(...)` / SDK call
and read true token counts from the response.

The demo writes auditable per-key spend, token totals, remaining budgets, and the
hard-stop result to `outputs/bonus_litellm_tracker.json`.
