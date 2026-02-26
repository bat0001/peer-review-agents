# Test Script Drift Observed During Eval Refactor Validation

**Status:** Open  
**Date:** 2026-02-11

## Summary

While validating the eval-batch refactor, two existing tests failed due to script drift unrelated
to the refactor implementation.

## Issue 1: `test/test_refactored_models.py`

- Failure:
  - `AttributeError: 'TestConfig' object has no attribute 'expert_parallel'`
- Cause:
  - `src/models/gec.py` now expects `config.expert_parallel`, but test's `TestConfig` omits it.

## Issue 2: `test/test_ep_engine.py`

- Failure:
  - `ValueError: too many values to unpack (expected 5)`
- Cause:
  - Test unpack signature is stale vs current engine return tuple in `ParallelExperts`.

## Impact

- Validation friction for multi-GPU EP test paths.
- Not evidence of regression in eval-batch changes.

## Proposed Follow-up

- Update local test configs/signatures to match current model/engine interfaces.
- Keep this as a separate cleanup from functional refactor work.
