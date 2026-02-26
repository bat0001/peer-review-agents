# CORE Eval Few-shot Failure on Small Task Subsets

**Status:** Open  
**Date:** 2026-02-11

## Summary

CORE eval can fail when `eval.core_metric_max_per_task` is too small for configured few-shot
sampling. The code samples `num_fewshot` exemplars from `len(data)-1`; if population is smaller,
Python raises a `ValueError`.

## Symptom

- Error:
  - `ValueError: Sample larger than population or is negative`
- Triggered in:
  - `src/eval/core.py` at `rng.sample(available_indices, num_fewshot)`

## Reproduction

```bash
CUDA_VISIBLE_DEVICES=2,3 /data2/hanchi/miniconda3/envs/nanochat/bin/torchrun --nproc_per_node=2 eval_core.py \
  eval.core_checkpoint_path=outputs/gec_shared_d8_G2E8_0.01B_ep8/gec_shared_d8_G2E8_0.01B_ep8/checkpoints/checkpoint_step_100_fixed.pt \
  eval.core_metric_max_per_task=8 \
  eval.core_eval_examples_per_forward=4
```

## Root Cause

After task-level shuffle and truncation (`max_per_task`), some datasets can become smaller than
their configured few-shot count + current sample exclusion, making `random.sample` invalid.

## Proposed Fix

Clamp few-shot count to available population:

- `effective_fewshot = min(num_fewshot, max(0, len(data) - 1))`

Alternative behavior:

- Skip task/eval item with explicit warning when population is insufficient.

## Impact

- Evaluation robustness issue (not model correctness).
- Affects fast smoke runs that intentionally use small `max_per_task`.
