# Bonus — real local model ($/token from real tok/s)

Run a tiny model on CPU, measure **real tokens/sec**, and compare the resulting
`$/1M-token` to the simulation. The default word-bigram model is fully offline
and uses only Python's standard library.

```bash
python bonus/local_model/run_local.py
```

For an optional downloaded model already present in the local Hugging Face cache:

```bash
pip install torch transformers
python bonus/local_model/run_local.py --backend transformers \
  --model sshleifer/tiny-gpt2 --tokens 64
```

The Transformers backend uses `local_files_only=True`, so it never downloads a
model unexpectedly. Results are written to `outputs/bonus_local_model.json`.
