# Metric Logging Architecture: Deadlock Prevention

**Date**: 2025-11-10
**Status**: Active design

## Problem Statement

In distributed training, GPU→CPU synchronization operations (`.item()`, `.numel()`, `.tolist()`) create barriers. When these operations occur in rank-divergent code (e.g., rank-0-only logging), they cause deadlocks:

1. Rank 0 enters logging, calls `.item()` on GPU tensor
2. Rank 0's CPU blocks waiting for GPU
3. Rank 0's GPU may need communication from rank 1's GPU
4. But rank 1's GPU is idle, waiting at a barrier
5. **Deadlock**: Circular dependency

Previous approach: discipline-based fixes (manually convert tensors before logging). **Problem**: Easy to forget, brittle, requires constant vigilance.

## Design Goal

**Make deadlocks structurally impossible** by enforcing API boundaries that prevent tensors from reaching rank-divergent code.

## Architecture

### Three-Zone Model

```
┌─────────────────────────────────────────────────────────────┐
│ GPU Zone (All Ranks)                                        │
│ - Metrics computed as tensors                               │
│ - All operations stay on GPU                                │
│ - No Python conversions                                     │
│                                                             │
│ Files: src/models/gec_shared/*.py, src/utils/routing_metrics.py │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Conversion Boundary (All Ranks)                            │
│ - Single explicit conversion point                          │
│ - ModelBase._metrics_to_scalars()                          │
│ - All ranks participate (no divergence)                    │
│ - Assertions enforce: tensors in, scalars out              │
│                                                             │
│ File: src/models/model_base.py:748-781                     │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ CPU Zone (Training Loop)                                    │
│ - Metrics are Python types (float, list)                   │
│ - Simple arithmetic for accumulation                       │
│ - Rank-divergent code is safe (no GPU operations)          │
│ - Assertions validate: no tensors allowed                  │
│                                                             │
│ Files: train.py:227-315, src/utils/logger.py               │
└─────────────────────────────────────────────────────────────┘
```

### Key Invariant

**`ModelOutput.metrics` always contains Python types, never tensors.**

This is enforced by:
1. Assertions in `ModelBase.forward()` after conversion
2. Assertions in training loop after receiving metrics
3. Assertions in logger at entry point
4. Assertions in `compute_routing_metrics()` for outputs

## Implementation

### 1. ModelBase: Owns Conversion

**Location**: `src/models/model_base.py`

```python
@staticmethod
def _metrics_to_scalars(metrics: dict) -> dict:
    """
    Convert tensor metrics to Python types.

    CRITICAL: This prevents distributed deadlocks by ensuring tensors
    never reach rank-divergent code in the training loop.

    Called in forward() so training loop only handles Python scalars/lists.
    """
    result = {}
    for k, v in metrics.items():
        # Assert: Input should be tensors
        assert torch.is_tensor(v), \
            f"Metric '{k}' is not a tensor (got {type(v)}). " \
            f"This indicates a bug in metric computation."

        # Convert: GPU tensor → CPU tensor → Python type
        v_cpu = v.detach().cpu()

        if v_cpu.numel() == 1:
            # Scalar metric
            result[k] = float(v_cpu.item())
        else:
            # Vector metric
            result[k] = v_cpu.tolist()

    return result
```

**Why in forward()**:
- Happens automatically, impossible to forget
- All ranks participate (no divergence)
- Single conversion point (easy to maintain)
- Training loop decoupled from tensor handling

### 2. Training Loop: Pure Python

**Location**: `train.py`

```python
# Accumulate metrics (simple Python arithmetic)
for k, v in output.metrics.items():
    # Assert: Model returned scalar metrics (defense in depth)
    assert not torch.is_tensor(v), \
        f"BUG: Model returned tensor metric '{k}'. " \
        f"Passing tensor-type metrics risks deadlocks."

    if isinstance(v, list):
        # Vector metric: element-wise accumulation
        routing_metrics[k] = [
            acc + val / grad_accum_steps
            for acc, val in zip(routing_metrics[k], v)
        ]
    else:
        # Scalar metric: simple addition
        routing_metrics[k] += v / grad_accum_steps
```

**Benefits**:
- No tensor operations
- No `.detach()`, `.clone()`, `.cpu()` calls
- Pure Python arithmetic
- Easy to understand and debug

### 3. Logger: Strict Validation

**Location**: `src/utils/logger.py`

```python
def log_metrics(self, step: int, metrics: dict) -> None:
    """Log metrics. NO TENSORS ALLOWED."""

    if not self.should_log:
        return

    # Assert: No tensors allowed (defense in depth)
    for key, value in metrics.items():
        assert not torch.is_tensor(value), \
            f"Tensor metric '{key}' passed to logger! " \
            f"Passing tensor-type metrics risks deadlocks."

        assert isinstance(value, (int, float, list, bool)), \
            f"Unexpected metric type for '{key}': {type(value)}"

    # ... proceed with logging
```

**Why assertions**:
- Fail fast if someone bypasses conversion
- Clear error message explains the problem
- Prevents silent bugs

### 4. Routing Metrics: Document Contract

**Location**: `src/utils/routing_metrics.py`

```python
def compute_routing_metrics(...) -> dict:
    """Compute routing metrics. Returns tensors (ModelBase converts)."""

    # ... compute metrics as tensors ...

    # Assert: All outputs are tensors (ModelBase will convert)
    for k, v in metrics.items():
        assert torch.is_tensor(v), \
            f"compute_routing_metrics() should return tensors, " \
            f"got {type(v)} for '{k}'"

    return metrics
```

## Defense in Depth

Multiple layers of protection ensure correctness:

| Layer | Location | Check | Action |
|-------|----------|-------|--------|
| 1 | `routing_metrics.py` | Outputs are tensors | Assert |
| 2 | `model_base.py` (pre-convert) | Inputs are tensors | Assert |
| 3 | `model_base.py` (post-convert) | Outputs are scalars | Assert |
| 4 | `train.py` (after forward) | Received metrics are scalars | Assert |
| 5 | `train.py` (before logging) | All metrics are scalars | Assert |
| 6 | `logger.py` (at entry) | No tensors in input | Assert |

**If a tensor leaks through**: Caught immediately with clear error message.

## Performance Improvements

Beyond deadlock prevention, this refactoring improved performance:

1. **Barriers only on logging steps**: Moved inside `if step % log_interval == 0`
2. **Evaluation rank-0 only**: No longer runs on all ranks
3. **Simpler accumulation**: Pure Python faster than tensor ops for small dicts

## Distributed Training Patterns

### Safe Patterns

```python
# ✅ All ranks compute, rank 0 logs
metrics_cpu = convert_to_python(metrics_gpu)  # All ranks
if rank == 0:
    logger.log(metrics_cpu)  # Safe: no GPU ops
dist.barrier()  # All ranks sync

# ✅ Conversion before divergence
for micro_step in range(grad_accum_steps):
    output = model(x, y)  # metrics already Python types
    accumulate(output.metrics)  # Pure Python
```

### Unsafe Patterns

```python
# ❌ Conversion in rank-divergent code
if rank == 0:
    logger.log(metrics_gpu)  # .item() called inside logger
    # Rank 0 blocks on GPU→CPU sync

# ❌ Conditional conversion
if step % log_interval == 0:
    metrics_cpu = convert(metrics_gpu)  # Only some steps
# Different ranks may convert at different times
```

## Why GPU→CPU Sync Causes Deadlocks

### PyTorch Async Execution Model

GPU operations are **asynchronous** by default:

```python
x = torch.randn(1000, 1000, device='cuda')
y = x @ x  # Queued, returns immediately
z = y + 1  # Also queued
# Python continues, GPU executes in background
```

`.item()` forces **synchronization**:

```python
value = y.item()  # Blocks until GPU completes y
```

### The Deadlock Sequence

In distributed training:

```
Time    Rank 0                          Rank 1
----    ------                          ------
T0      forward() completes             forward() completes
T1      if rank == 0:                   Reaches barrier
T2        loss.item() ← BLOCKS          Waits for rank 0
        (GPU→CPU sync)
T3      GPU busy with computation       GPU idle
T4      GPU needs data from rank 1      Can't send (waiting for rank 0)

        ← DEADLOCK: Circular dependency →
```

**Key insight**: `.item()` in rank-divergent code creates circular dependency between CPUs and GPUs.

## Migration Guide

### For New Metrics

1. Compute metric as tensor in MLP forward pass
2. Return in metrics dict
3. Done! ModelBase converts automatically

### For Existing Code

**If you see**:
```python
scalar = tensor.item()
logger.log({'metric': scalar})
```

**Change to**:
```python
# Nothing! Conversion happens in ModelBase.forward()
# Just pass metrics through
```

## Testing

Verified with both single-GPU and multi-GPU:

```bash
# Single GPU
CUDA_VISIBLE_DEVICES=0 python train.py +experiment=debug training.max_steps=3

# Multi-GPU (deadlock test)
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 \
  train.py +experiment=debug training.max_steps=3
```

Both pass without deadlocks.

## Expert Parallelism (EP) Considerations

With EP, additional deadlock sources exist beyond `.item()` calls:

### EP-Specific Deadlock: Rank-Divergent Forward Pass

With EP, `model.forward()` uses all-to-all collectives (`dist.all_gather`, `all_to_all`).
**Any code that calls model.forward() must run on ALL ranks.**

**Dangerous pattern**:
```python
# ❌ BAD: Only rank 0 runs forward
if rank == 0:
    evaluate(model, ...)  # forward() needs all-to-all!
dist.barrier()  # Rank 1 waits here → DEADLOCK
```

**Safe pattern**:
```python
# ✅ GOOD: All ranks run forward, only rank 0 logs
if expert_parallel:
    evaluate(model, ..., logger if rank == 0 else None)
else:
    if rank == 0:
        evaluate(model, ..., logger)
dist.barrier()
```

**Files implementing this**: `train.py` (evaluation section)

## References

- Bug history: `memory/bugs/deadlock_item_calls.md`
- Related designs: `memory/design/logging_architecture.md`
- PyTorch docs: Asynchronous execution and `.item()` synchronization

## Summary

**Problem**: Distributed deadlocks from GPU→CPU sync in rank-divergent code

**Solution**: Enforce API boundary - tensors stay in GPU zone, scalars in CPU zone

**Implementation**: ModelBase converts in `forward()`, training loop validates

**Result**: Deadlocks structurally impossible, simpler code, better performance
