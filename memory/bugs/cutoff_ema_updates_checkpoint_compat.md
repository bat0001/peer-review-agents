# `cutoff_ema_updates` Checkpoint Compatibility

**Status:** Documented behavior (eval compatibility path in place)

## Summary
Older checkpoints may contain only `*.mlp.engine.cutoff_ema` and no
`*.mlp.engine.cutoff_ema_updates` buffer. Newer model code registers
`cutoff_ema_updates`, so strict state-dict loading can fail even when the
routing state (`cutoff_ema`) is valid.

## Symptoms
- Eval script fails during `load_state_dict` with:
  - `Missing key(s) in state_dict: "...cutoff_ema_updates"...`
- Checkpoint inspection shows:
  - `cutoff_ema` keys present
  - `cutoff_ema_updates` keys absent

## Root Cause
`cutoff_ema_updates` is a newer bookkeeping buffer (EMA update counter).
It is not the threshold value used for routing decisions; `cutoff_ema` remains
the routing-critical state.

## Intended Behavior
- Threshold routing semantics should continue to use `cutoff_ema`.
- Missing `cutoff_ema_updates` in older checkpoints should not block eval.
- Any other key mismatch should still fail fast.

## Eval Loader Policy
In `eval_moe_visualization.py`, checkpoint loading uses a compatibility guard:
- Load with `strict=False`
- Allow missing keys only if they end with `cutoff_ema_updates`
- Raise on any unexpected keys or any other missing keys

This preserves strictness for real schema errors while allowing older
checkpoints that still have correct `cutoff_ema` state.
