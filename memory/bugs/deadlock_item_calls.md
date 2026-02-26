# Multi-GPU Deadlock Prevention: .item() and Tensor Synchronization

**Last Updated**: 2025-11-10
**Status**: Active prevention guidelines
**Severity**: Critical (deadlocks multi-GPU training)

## Summary

Multi-GPU training can deadlock when `.item()` calls or tensor operations occur in the forward pass, creating GPU→CPU synchronization barriers that cause rank divergence. This document describes the architectural solution and prevention patterns.

## The 2025-11-10 Architecture: Metric Pipeline Separation

**Root solution**: Enforce clean separation between GPU tensors and Python scalars via API boundaries, not code review.

```
GPU Zone (tensors) → Conversion Boundary → CPU Zone (Python types)
      ↓                      ↓                        ↓
  ModelBase             _metrics_to_scalars()    train.py + Logger
  (computes)             (converts once)          (logs safely)
```

**Key invariant**: `ModelOutput.metrics` always contains Python types (float/list), never tensors.

### Implementation

**ModelBase**: Converts all metrics after forward pass completes
```python
@staticmethod
def _metrics_to_scalars(metrics: dict) -> dict:
    """Convert tensor metrics to Python types (prevents deadlocks)."""
    result = {}
    for k, v in metrics.items():
        assert torch.is_tensor(v), f"Metric '{k}' must be tensor"
        v_cpu = v.detach().cpu()
        if v_cpu.numel() == 1:
            result[k] = float(v_cpu.item())
        else:
            result[k] = v_cpu.tolist()
    return result

# In forward():
scalar_metrics = self._metrics_to_scalars(aggregated_metrics)
return ModelOutput(loss=loss, logits=logits, metrics=scalar_metrics)
```

**Training loop**: Pure Python arithmetic on scalars/lists
```python
for k, v in output.metrics.items():
    assert not torch.is_tensor(v), "Passing tensor-type metrics risks deadlocks"

    if isinstance(v, list):
        routing_metrics[k] = [acc + val/grad_accum_steps
                             for acc, val in zip(routing_metrics[k], v)]
    else:
        routing_metrics[k] += v / grad_accum_steps
```

**Logger**: Strict validation, no tensor handling
```python
for key, value in metrics.items():
    assert not torch.is_tensor(value), \
        f"Tensor metric '{key}' passed to logger! Passing tensor-type metrics risks deadlocks."
    assert isinstance(value, (int, float, list, bool)), \
        f"Unexpected metric type for '{key}': {type(value)}"
```

## Why .item() Causes Deadlocks

### The Mechanism

1. `.item()` triggers GPU→CPU synchronization (blocks until value available)
2. In multi-GPU training, different ranks may execute different code paths
3. If one rank calls `.item()` in a conditional that others skip → deadlock
4. Loops amplify the problem: per-expert loop = 16× sync barriers

### Dangerous Patterns

```python
# ❌ BAD: Implicit .item() in conditionals
if n_above > k_max:  # n_above is tensor → implicit .item()
    ...

# ❌ BAD: Explicit .item() in per-expert loop
for expert_idx in range(n_experts):
    k = int(k_actual[expert_idx].item())  # 16× sync barriers!

# ❌ BAD: .item() in forward pass
n_above = above_mask.sum().item()  # Sync in hot path
```

### Safe Patterns

```python
# ✅ GOOD: Keep as tensors, let ModelBase convert
n_above = above_mask.sum()  # Tensor
metrics['capacity_overflow'] = (n_above > k_max).float().mean()  # Still tensor

# ✅ GOOD: Batch convert before loop (single sync)
k_actual_cpu = k_actual.cpu()  # One GPU→CPU transfer
for expert_idx in range(n_experts):
    k = int(k_actual_cpu[expert_idx])  # No sync, already on CPU

# ✅ GOOD: Unavoidable .item() for allocation (document it)
# EXCEPTION: .item() required for tensor allocation (sync unavoidable)
actual_k_max = int(k_actual.max().item())
```

## Recent Fix: shared_capacity_batched.py (2025-11-10)

### Problem
Multiple `.item()` calls in forward pass creating sync barriers and unused computations.

### Changes

**1. Removed unnecessary .item() calls** (lines 139-140)
```python
# Before (BAD):
capacity_overflow = hit_max.sum().item()  # Sync + never used
capacity_underflow = hit_min.sum().item()  # Sync + never used

# After (GOOD):
# Removed entirely - compute_routing_metrics() handles this
```

**2. Documented unavoidable .item()** (line 145)
```python
# EXCEPTION: .item() required for tensor allocation (sync unavoidable)
actual_k_max = int(k_actual.max().item())
```

**3. Batched per-expert .item() calls** (line 197)
```python
# Before (BAD): 16× sync barriers
for expert_idx in range(n_routed_experts):
    k = int(k_actual[expert_idx].item())  # Sync per expert!

# After (GOOD): 1× sync
k_actual_cpu = k_actual.cpu()  # Single GPU→CPU transfer
for expert_idx in range(n_routed_experts):
    k = int(k_actual_cpu[expert_idx])  # No sync
```

**4. Fixed capacity metrics computation** (lines 180-182)
```python
# Before (BAD): Hardcoded zeros
if capacity_enabled:
    metrics['capacity_overflow_rate'] = torch.tensor(0.0, device=x.device)

# After (GOOD): Pass to compute_routing_metrics()
metrics = compute_routing_metrics(
    ...
    above_counts=above_counts if capacity_enabled else None,
    k_min=k_min if capacity_enabled else None,
    k_max=k_max if capacity_enabled else None,
)
# compute_routing_metrics() now computes capacity metrics properly
```

### Testing

✅ **Test 1**: 2 GPUs, 6 steps, threshold warmup
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 train.py \
  mlp=gec_shared_capacity +experiment=debug \
  training.max_steps=6 training.threshold_warmup_steps=3
```
Result: Passed, switched to threshold at step 3

✅ **Test 2**: 2 GPUs, 5 steps, capacity from step 0
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 train.py \
  mlp=gec_shared_capacity +experiment=debug \
  training.max_steps=5 training.threshold_warmup_steps=0
```
Result: Passed, capacity metrics correctly logged (e.g., `capacity_overflow_rate: 1.0000`)

✅ **Test 3**: 2 GPUs, 20 steps, extended run
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 train.py \
  mlp=gec_shared_capacity +experiment=debug \
  training.max_steps=20 training.threshold_warmup_steps=5
```
Result: Passed, no deadlocks, capacity metrics working (`capacity_overflow_rate: 0.8369`)

## Prevention Guidelines

### ✅ Safe Practices

**In forward pass:**
- Return ALL metrics as tensors
- Use tensor operations for computations
- Batch GPU→CPU transfers when unavoidable
- Document any .item() exceptions clearly

**In training loop:**
- Only handle Python types (float, int, list)
- Use simple arithmetic for accumulation
- Assert no tensors received from model

**In logging:**
- Only accept Python types
- Assert no tensors at entry point
- Never call tensor methods

### ❌ Dangerous Practices

**Never in forward/backward pass:**
- `.item()` calls (except documented exceptions)
- Tensor comparisons in Python `if` statements
- Per-expert/per-layer `.item()` loops
- Conditional code paths with tensor→scalar conversion

### Exceptions

Some `.item()` calls are unavoidable:
- **Tensor allocation**: `torch.zeros(int(size.item()), ...)`
- **Control flow for padding**: Computing max tokens across experts

**Requirements for exceptions:**
1. Document with comment: `# EXCEPTION: .item() required for [reason]`
2. Ensure all ranks execute the same code path
3. Minimize number of such calls

## File Locations

**Core architecture:**
- `src/models/model_base.py` - `_metrics_to_scalars()` implementation
- `train.py` - Metric accumulation and assertions
- `src/utils/logger.py` - Logging validation
- `src/utils/routing_metrics.py` - Metric computation (returns tensors)

**Fixed models:**
- `src/models/gec_shared/shared_capacity_batched.py` - 2025-11-10 fix
- `src/models/gec_shared/shared_capacity_threshold.py` - Earlier fixes

## References

- Design document: `memory/design/metric_logging_architecture.md`
- Full debugging history: `memory/archive/debugging/deadlock_item_calls_full_history.md`
- PyTorch DDP behavior: `.item()` triggers CPU sync and blocks until tensor value available
