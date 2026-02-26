# Threshold Warmup Eval Used Top‑K (Resolved 2026-01-19)

## Summary
Evaluation was running top‑k routing during threshold warmup because explicit
`routing_mode='topk'` overrides the training/eval auto‑selection. This led to
eval loss/core scores being computed with top‑k when warmup steps were enabled.

## Root Cause
`GECMLP`/`GECSharedMLP` prioritized `routing_mode` over `model.eval()`. The
training loop set `routing_mode='topk'` when `threshold_warmup_steps >= 0`,
so eval inherited top‑k even though it should be threshold.

## Fix
- Eval routing is now always threshold in `GECMLP`/`GECSharedMLP`.
- `routing_mode` is training‑only and restricted to `'topk' | 'threshold'`.
- Removed the warmup “pin top‑k” in `train.py`; warmup only switches to
  threshold at the configured step.
- Docs/configs/tests updated to drop `None`/auto routing mode.

## Impact / Compatibility
Breaking change for configs that set `routing_mode: null` or code calling
`set_routing_mode(None)`. Replace with `routing_mode: "topk"`.

## Verification
Lightweight tests updated to use train mode for top‑k and eval for threshold.
Run: `pytest test/test_refactored_models.py` and
`pytest test/test_gec_shared_shared_weight.py`.
