"""Benchmark a real local CPU generation loop and calculate $/1M-token.

The default built-in bigram model requires only the standard library, making
the bonus reproducible offline. An optional Hugging Face backend benchmarks a
downloaded causal LM when torch/transformers are available.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = """
gpu finops measures useful tokens per dollar and per watt .
model flops utilization reveals compute efficiency while gpu utilization only shows activity .
prompt caching batch inference model routing and checkpointed spot capacity reduce cost .
carbon aware scheduling moves interruptible training to cleaner electricity regions .
"""


def _economics(model: str, backend: str, generated_tokens: int, seconds: float, rate_hr: float) -> dict:
    tokens_per_second = generated_tokens / seconds if seconds > 0 else 0.0
    cost_per_million = (
        (seconds / 3600.0) * rate_hr / max(1, generated_tokens) * 1e6
    )
    return {
        "model": model,
        "backend": backend,
        "generated_tokens": generated_tokens,
        "elapsed_seconds": round(seconds, 6),
        "tokens_per_second": round(tokens_per_second, 2),
        "cpu_rate_usd_per_hour": rate_hr,
        "cost_usd_per_million_tokens": round(cost_per_million, 6),
        "simulated_small_model_usd_per_million_tokens": 0.30,
    }


def benchmark_builtin(token_count: int, rate_hr: float) -> dict:
    """Train and sample a tiny word-bigram model entirely on the local CPU."""
    training_tokens = CORPUS.lower().split()
    transitions: dict[str, list[str]] = defaultdict(list)
    for left, right in zip(training_tokens, training_tokens[1:]):
        transitions[left].append(right)
    fallback = list(dict.fromkeys(training_tokens))
    rng = random.Random(25)
    current = "gpu"
    started = time.perf_counter()
    checksum = 0
    for _ in range(token_count):
        choices = transitions.get(current, fallback)
        current = choices[rng.randrange(len(choices))]
        checksum = (checksum * 33 + sum(ord(char) for char in current)) & 0xFFFFFFFF
    elapsed = time.perf_counter() - started
    result = _economics("offline-word-bigram", "builtin", token_count, elapsed, rate_hr)
    # Keep a side effect so an optimizing runtime cannot discard generation.
    result["generation_checksum"] = checksum
    return result


def benchmark_transformers(model_id: str, token_count: int, rate_hr: float) -> dict:
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:
        raise RuntimeError("torch + transformers are required for this backend") from exc

    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(model_id, local_files_only=True)
    prompt = "GPU FinOps measures cost per useful token because"
    inputs = tokenizer(prompt, return_tensors="pt")
    started = time.perf_counter()
    output = model.generate(**inputs, max_new_tokens=token_count, do_sample=False)
    elapsed = time.perf_counter() - started
    generated = output.shape[-1] - inputs["input_ids"].shape[-1]
    return _economics(model_id, "transformers", generated, elapsed, rate_hr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("builtin", "transformers"), default="builtin")
    parser.add_argument("--tokens", type=int, default=50_000)
    parser.add_argument("--model", default=os.environ.get("LAB_MODEL", "sshleifer/tiny-gpt2"))
    args = parser.parse_args(argv)
    if args.tokens <= 0:
        parser.error("--tokens must be positive")

    rate_hr = float(os.environ.get("LAB_CPU_RATE_HR", "0.10"))
    try:
        if args.backend == "transformers":
            result = benchmark_transformers(args.model, args.tokens, rate_hr)
        else:
            result = benchmark_builtin(args.tokens, rate_hr)
    except Exception as exc:
        print(f"[error] {exc}")
        print("Use --backend builtin for the dependency-free offline benchmark.")
        return 1

    output_path = os.path.join(ROOT, "outputs", "bonus_local_model.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print(
        f"model={result['model']} backend={result['backend']} "
        f"tokens={result['generated_tokens']} time={result['elapsed_seconds']:.4f}s"
    )
    print(f"REAL throughput: {result['tokens_per_second']:,.1f} tok/s on CPU")
    print(
        f"REAL ~${result['cost_usd_per_million_tokens']:,.6f}/1M-token "
        "at the configured CPU hourly rate"
    )
    print("artifact:", os.path.relpath(output_path, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
