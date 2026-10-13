"""Per-key cost attribution and hard budget-stop demo (no API key needed)."""
from __future__ import annotations

import json
import os

try:
    from .tracker import BudgetExceeded, CostTracker
except ImportError:  # direct script execution
    from tracker import BudgetExceeded, CostTracker

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    tracker = CostTracker(budgets={"team-chat": 0.05, "team-eval": 100.0})
    blocked_after = None
    blocked_message = ""
    for index in range(40):
        try:
            tracker.complete(
                "team-chat",
                "large",
                "Summarize this very long document " * 30,
            )
        except BudgetExceeded as exc:
            blocked_after = index
            blocked_message = str(exc)
            print(f"BLOCKED after {index} chat requests: {exc}")
            break

    for _ in range(5):
        tracker.complete(
            "team-eval",
            "small",
            "classify: positive or negative?",
            batch=True,
        )

    result = tracker.summary()
    result["blocked_after_requests"] = blocked_after
    result["budget_guard_triggered"] = blocked_after is not None
    result["blocked_message"] = blocked_message
    output_path = os.path.join(ROOT, "outputs", "bonus_litellm_tracker.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print("\nper-key spend:", tracker.report())
    print("requests logged:", len(tracker.log))
    print("artifact:", os.path.relpath(output_path, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
