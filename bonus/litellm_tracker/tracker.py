"""A tiny LiteLLM-style token-cost tracker with per-API-key budget caps.

The §10 "token tier" of cost observability: attribute $/request per key/team and
HARD-STOP requests that would blow the budget. Mock backend — no API key needed.
"""
from __future__ import annotations
import os, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finops import pricing

MODEL_PRICES = {  # $/1M (input, output)
    "small": (0.20, 0.40),
    "large": (3.00, 15.00),
}


class BudgetExceeded(Exception):
    pass


class CostTracker:
    def __init__(self, budgets: dict | None = None):
        self.budgets = budgets or {}          # api_key -> monthly USD cap
        self.spend = defaultdict(float)       # api_key -> USD spent
        self.log = []

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)         # ~4 chars/token rule of thumb

    def complete(self, api_key: str, model: str, prompt: str,
                 max_output_tokens: int = 256, cached_input_tokens: int = 0,
                 batch: bool = False) -> dict:
        if model not in MODEL_PRICES:
            raise ValueError(f"unknown model tier: {model}")
        if max_output_tokens < 0:
            raise ValueError("max_output_tokens must be non-negative")
        in_tok = self._estimate_tokens(prompt)
        out_tok = max_output_tokens
        pin, pout = MODEL_PRICES[model]
        cost = pricing.request_cost(in_tok, out_tok, pin, pout,
                                    cached_in=cached_input_tokens, batch=batch)
        cap = self.budgets.get(api_key)
        if cap is not None and self.spend[api_key] + cost > cap:
            raise BudgetExceeded(
                f"key={api_key} would spend ${self.spend[api_key]+cost:.4f} > cap ${cap:.2f}")
        self.spend[api_key] += cost
        rec = {
            "ts": time.strftime("%H:%M:%S"),
            "key": api_key,
            "model": model,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cached_input_tokens": min(max(0, cached_input_tokens), in_tok),
            "batch": batch,
            "cost_usd": round(cost, 6),
        }
        self.log.append(rec)
        # MOCK response (swap this block for a real provider call)
        rec["text"] = f"[mock {model}] ok ({in_tok} in / {out_tok} out)"
        return rec

    def report(self) -> dict:
        return {k: round(v, 4) for k, v in self.spend.items()}

    def remaining_budget(self, api_key: str) -> float | None:
        """Return remaining USD for a capped key, or None for an uncapped key."""
        cap = self.budgets.get(api_key)
        return None if cap is None else round(max(0.0, cap - self.spend[api_key]), 4)

    def summary(self) -> dict:
        """Portable observability payload suitable for a dashboard or audit log."""
        by_key = {}
        keys = set(self.spend) | set(self.budgets)
        for key in sorted(keys):
            requests = [row for row in self.log if row["key"] == key]
            by_key[key] = {
                "requests": len(requests),
                "spend_usd": round(self.spend[key], 6),
                "budget_usd": self.budgets.get(key),
                "remaining_usd": self.remaining_budget(key),
                "input_tokens": sum(row["input_tokens"] for row in requests),
                "output_tokens": sum(row["output_tokens"] for row in requests),
            }
        return {"requests_logged": len(self.log), "by_key": by_key}
