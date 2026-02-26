# Eval Batch Forward Interface

**Date:** 2026-02-11  
**Status:** Active

## Summary

Introduce a generic model-facing eval prefill API so eval callers do not own EP-specific
distributed shape alignment. This API is designed for CORE first, but intentionally generic
for reuse by other eval paths.

## API Contract

Location: `src/models/model_base.py`

- `EvalBatchForwardResult`
  - `losses`: token CE losses, shape `(B_exec, T_exec)`, last token set to `NaN`
  - `predictions`: argmax token predictions, shape `(B_exec, T_exec)`
  - `valid_rows`: boolean mask, shape `(B_exec,)`

- `BaseGPT.forward_eval_batch(input_ids, pad_token_id=0) -> EvalBatchForwardResult`
  - Input is local `LongTensor[B_local, T_local]` on the current device.
  - Caller provides only local tensor validity (2D, `torch.long`), not global shape matching.
  - Model handles EP distributed alignment internally when needed.

## Distributed Behavior (EP)

`BaseGPT._prepare_ep_eval_inputs(...)` handles eval-step alignment:

- Ranks exchange local shape bounds via collectives.
- Inputs are padded to step-global `(B_exec, T_exec)` before entering regular forward.
- Dummy rows are represented via `valid_rows=False`.

This keeps collective ordering inside model code and prevents eval call sites from duplicating
EP shape/lockstep logic.

## Caller Responsibilities

- Build task-specific local batches/microbatches and metadata.
- Call `forward_eval_batch(...)`.
- Score only real rows (or rows mapped to real examples); ignore any internal dummies via
  `valid_rows`.
- Avoid adding distributed shape collectives in eval caller logic.

## Non-goals

- This interface does not implement fully ragged EP routing internals.
- This interface does not replace task scoring logic.
- This interface is for eval-prefill paths, not training forward.

## Rationale

- Keeps eval entrypoints thin and model-agnostic.
- Centralizes EP-specific shape handling in one place.
- Provides one stable boundary for future eval reuse.
