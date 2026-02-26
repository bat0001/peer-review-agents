# Cutoff EMA Sync False Diagnosis (2025-11-07 to 2025-11-10)

**Status**: ARCHIVED - Debugging timeline that led to false conclusion
**Actual Issue**: Metric pipeline (tensors reaching logger), not cutoff EMA sync
**Resolution**: See `memory/bugs/deadlock_item_calls.md` (2025-11-10 section)

## Background

During 2025-11-07 to 2025-11-10, we experienced deadlocks in multi-GPU training with threshold routing. This document archives the debugging timeline that incorrectly attributed the issue to cutoff EMA synchronization.

## False Hypothesis

**What we thought**: Cutoff EMA sync in `BaseGPT.step_complete()` was causing deadlocks due to:
- BF16/FP32 dtype mismatches
- Different ranks having different `cutoff_ema` attributes
- In-place `dist.all_reduce` operations

## Debugging Timeline (Archived for Historical Reference)

### 2025-11-07
After introducing micro-batch cutoff accumulation, noticed occasional hangs when switching to threshold routing. Attributed to rare reduce_scatter stalls; deemed transient.

### 2025-11-08
Reproducible hang on 4-GPU job. Rank logs showed all micro-steps completing; stall occurs inside `BaseGPT.step_complete`.

### 2025-11-09
Confirmed that the deadlock happens on first call to `dist.all_reduce` for `cutoff_ema`. Replacing with `dist.all_reduce(broadcast_tensor)` still hangs.

**Hypothesis at this point**: dtype/device mismatch or rank divergence in cutoff_ema attributes.

### 2025-11-10 (Morning)
Instrumented with `dist.barrier()` before/after the sync; barrier before returns, after blocks. Dumped tensor metadata: some ranks had `cutoff_ema` in `torch.bfloat16`, others in `torch.float32`. Also noted that layers without threshold routing skipped the `all_reduce`.

**This led to the false conclusion that EMA sync was the issue.**

### 2025-11-10 (Afternoon)
**Breakthrough**: Fixed the metric pipeline refactoring (moved tensor→scalar conversion to ModelBase). Tested multi-GPU capacity threshold training - **NO DEADLOCKS**.

**Realization**: The deadlock was never about cutoff EMA sync. It was about tensors reaching the rank-divergent logger code in the training loop.

## Proposed Fix (Never Implemented - Was Based on Wrong Diagnosis)

This proposed fix addressed a problem that didn't exist:

### Add `sync_cutoff_state()` to RouterMixin

```python
def sync_cutoff_state(self) -> None:
    import torch.distributed as dist

    if not dist.is_initialized() or dist.get_world_size() == 1:
        return

    with torch.no_grad():
        ema_cpu = self.cutoff_ema.detach().to(dtype=torch.float32, device='cpu')
        count_cpu = None
        if hasattr(self, 'cutoff_ema_count'):
            count_cpu = self.cutoff_ema_count.detach().to(dtype=torch.float32, device='cpu')

        payload = (ema_cpu, count_cpu)
        gathered = [None for _ in range(dist.get_world_size())]
        dist.all_gather_object(gathered, payload)

        ema_mean = torch.stack([ema for ema, _ in gathered], dim=0).mean(dim=0)
        self.cutoff_ema.copy_(ema_mean.to(dtype=self.cutoff_ema.dtype, device=self.cutoff_ema.device))

        if count_cpu is not None:
            count_mean = torch.stack([cnt for _, cnt in gathered], dim=0).mean(dim=0)
            self.cutoff_ema_count.copy_(
                count_mean.reshape_as(self.cutoff_ema_count).to(
                    dtype=self.cutoff_ema_count.dtype,
                    device=self.cutoff_ema_count.device
                )
            )
```

**Why this wasn't needed**: The existing batched implementation in `model_base.py:596-647` was already correct. It was doing exactly this (CPU FP32 conversion + all_gather_object), just in a more efficient batched way.

## Actual Root Cause

The real issue was in the metric pipeline:

```python
# BAD (before fix):
output = model(x, y)  # Returns metrics as tensors
# ... training loop accumulates tensors ...
if rank == 0:
    logger.log_metrics(step, metrics)  # Tensors reach rank-divergent code
    # Logger calls .item() on tensors → DEADLOCK
```

The fix was to move tensor→scalar conversion into `ModelBase.forward()`:

```python
# GOOD (after fix):
output = model(x, y)  # ModelBase converts metrics to Python types
# ... training loop accumulates Python scalars ...
if rank == 0:
    logger.log_metrics(step, metrics)  # Already Python types → SAFE
```

## Key Lessons

1. **Correlation ≠ Causation**: Deadlock during `step_complete()` doesn't mean `step_complete()` is the problem

2. **Test thoroughly before concluding**: We attributed the issue to EMA sync because that's where we observed the hang, but the actual issue was earlier in the pipeline

3. **Zone boundaries matter**: The problem was tensors crossing from GPU Zone (forward pass) into CPU Zone (rank-divergent logging) without proper conversion

4. **Existing implementation was good**: The batched `all_gather_object` in `model_base.py` was actually well-designed - efficient and correct

## References

- **Actual fix**: `memory/bugs/deadlock_item_calls.md` (2025-11-10 section)
- **Design document**: `memory/design/metric_logging_deadlock_prevention.md`
- **Current working implementation**: `src/models/model_base.py:596-647`

## Deprecation Note

This document is archived to preserve the debugging journey. Future developers encountering similar issues should:

1. Check the metric pipeline first (are tensors reaching rank-divergent code?)
2. Verify the Three-Zone Model is followed (GPU Zone → Conversion Boundary → CPU Zone)
3. Test with the actual fix (metric pipeline) before pursuing other hypotheses

The cutoff EMA sync implementation was correct all along and required no changes.
