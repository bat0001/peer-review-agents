# Torch.compile Recompilation Bug

**Date**: 2025-12-05
**Status**: Fixed
**Related**: `memory/design/cutoff_accumulation.md`

## The Problem

During training with `torch.compile`, we observed a `torch._dynamo hit config.recompile_limit` warning, causing the model to fall back to eager mode or repeatedly recompile.

```
[rank4]:W1205 19:25:00.485000 1680707 site-packages/torch/_dynamo/convert_frame.py:1016] [4/8] torch._dynamo hit config.recompile_limit (8)
[rank4]:W1205 19:25:00.485000 1680707 site-packages/torch/_dynamo/convert_frame.py:1016] [4/8]    function: 'forward_topk' (/data2/hanchi/nano_gec_clean/src/models/engines/engine.py:82)
[rank4]:W1205 19:25:00.485000 1680707 site-packages/torch/_dynamo/convert_frame.py:1016] [4/8]    last reason: 4/7: len(self.cutoff_accumulator) == 7
```

### Root Cause

The `ExpertEngine` was using a Python list (`self.cutoff_accumulator`) to accumulate cutoff statistics from micro-batches during gradient accumulation.

```python
# Old implementation
if self.cutoff_accumulator is None:
    self.cutoff_accumulator = []
self.cutoff_accumulator.append(cutoffs)
```

`torch.compile` (Dynamo) treats the length of a list as part of the graph state. Since the list length grew with each micro-batch (1, 2, 3, ...), Dynamo triggered a recompilation for every new length. Eventually, it hit the default recompile limit (8) and stopped optimizing effectively.

## The Solution

We replaced the dynamic list accumulation with static in-place tensor accumulation.

### Implementation Details

1.  **State Buffers**: Instead of a list, we register two persistent buffers:
    ```python
    self.register_buffer('cutoff_accum_sum', torch.zeros(n_routed_experts), persistent=False)
    self.register_buffer('cutoff_accum_count', torch.zeros(1, dtype=torch.long), persistent=False)
    ```

2.  **In-Place Accumulation**: In `forward_topk` and `forward_threshold`, we accumulate in-place:
    ```python
    # New implementation
    self.cutoff_accum_sum.add_(cutoffs.detach())
    self.cutoff_accum_count.add_(1)
    ```

3.  **Finalization**: At the step boundary, we compute the mean from these tensors:
    ```python
    cutoff_mean = self.cutoff_accum_sum / self.cutoff_accum_count
    # ... update EMA ...
    self.cutoff_accum_sum.zero_()
    self.cutoff_accum_count.zero_()
    ```

### Benefits

-   **Static Graph**: The operations are now standard tensor ops with static shapes.
-   **No Recompilation**: `torch.compile` sees a single consistent graph structure regardless of the accumulation step.
-   **Equivalent Logic**: Mathematically equivalent to the arithmetic mean of the list elements.

## Verification

The fix was verified by observing the removal of `recompile_limit` warnings in the training logs. The EMA logic remains functionally identical.

