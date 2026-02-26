# Multi-GPU Deadlock from .item() Calls in Forward Pass

**Date**: 2025-11-05
**Status**: Fixed (initial); see 2025-11-09 regression note below
**Severity**: Critical (deadlocks multi-GPU training)

## Summary

Multi-GPU training with capacity threshold model deadlocked after step 0. Root cause: multiple `.item()` calls in forward pass creating GPU→CPU synchronization barriers that cause rank divergence.

## Symptoms

- Single-GPU training: works fine
- Multi-GPU training: completes step 0, then hangs indefinitely
- No error messages, just silent hang
- Timeout after 120+ seconds

## Root Cause

### Primary Culprit: Implicit .item() in Tensor Comparisons

**Location**: `src/models/gec_shared/shared_capacity_threshold.py:145-148`

```python
# BAD: Implicit .item() calls in if statements
if n_above > k_max:  # ← n_above is tensor, triggers .item()
    ...
elif n_above < k_min:  # ← Another .item()
    ...
```

**Why this deadlocks**:
1. Called **per-expert** in training loop (16 experts × multiple layers)
2. Each tensor comparison implicitly calls `.item()` for GPU→CPU sync
3. Happens only when `capacity_enabled` (conditional execution)
4. In multi-GPU, different ranks may diverge on which code paths execute
5. Results in some GPUs waiting indefinitely for others

### Secondary Issues

**Location**: `src/utils/routing_metrics.py:99, 105`

```python
# BAD: .item() in metric computation
idx = idx_buf.item() % history.shape[0]
n_samples = min(idx_buf.item(), history.shape[0])
```

**Why problematic**:
- Called during forward pass for representative layers only (conditional)
- Creates sync barriers in temporal tracking
- Less severe than capacity loop (only 5 layers), but still contributes

**Location**: `src/models/gec_shared/shared_capacity_threshold.py:135`

```python
# BAD: .item() in per-expert loop
n_above = above_mask.sum().item()
```

## The Fix

### Fix 1: Batch Convert Tensors Before Conditionals

```python
# GOOD: Convert once, use multiple times
n_above_int = int(n_above)  # Single GPU→CPU sync
k_actual_int = int(k_actual)

if n_above_int > k_max:  # No additional sync
    ...
elif n_above_int < k_min:  # No additional sync
    ...
```

**Files changed**:
- `src/models/gec_shared/shared_capacity_threshold.py:144-147`

### Fix 2: Use int() for Tensor Indexing

```python
# GOOD: Use int() instead of .item()
idx = int(idx_buf) % history.shape[0]
n_samples = min(int(idx_buf), history.shape[0])
```

**Files changed**:
- `src/utils/routing_metrics.py:101, 107`

### Fix 3: Keep Tensors Until Absolutely Necessary

```python
# GOOD: Keep as tensor through computation
n_above = above_mask.sum()  # Tensor, not scalar
would_have_k_per_expert.append(n_above)  # Still tensor
k_actual = torch.clamp(n_above, k_min, k_max)  # Tensor ops
```

**Files changed**:
- `src/models/gec_shared/shared_capacity_threshold.py:135, 139, 142`

## Key Insights

1. **Implicit .item() is dangerous**: Tensor comparisons in Python `if` statements trigger hidden `.item()` calls
2. **Loops amplify the problem**: Per-expert loop = 16× sync barriers per forward pass
3. **Conditional execution creates divergence**: Different ranks executing different code paths → deadlock
4. **Location matters**: `.item()` in logger (after backward) is fine; in forward pass is not
5. **int() vs .item()**: Functionally similar but `int()` makes the sync explicit

## Prevention Guidelines

### ✅ Safe .item() Usage
- In logging code (after backward/optimizer step)
- In `torch.no_grad()` contexts for rare operations
- For converting **scalar** metrics to Python for wandb
- Example: `logger.log_metrics()` converts tensors with `.item()`

### ❌ Dangerous .item() Usage
- Inside forward/backward pass
- In per-expert or per-layer loops
- In conditional code paths that may differ across ranks
- Before DDP synchronization points

### Best Practice
```python
# BAD: Multiple syncs in loop
for expert_idx in range(n_experts):
    n = count_tensor.sum().item()  # Sync!
    if n > threshold:  # Another implicit sync!
        ...

# GOOD: Batch conversion
for expert_idx in range(n_experts):
    n_tensor = count_tensor.sum()  # Keep as tensor
    would_have.append(n_tensor)

# Convert once after loop
n_int = int(n_tensor)  # Single sync
if n_int > threshold:  # No additional sync
    ...
```

## Testing

Multi-GPU training with capacity threshold should now complete without deadlock:

```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 \
  train.py +experiment=debug mlp=gec_shared_capacity \
  model_size=tiny training.max_steps=10
```

## Related Issues

- None (first occurrence)
- This pattern should be audited in other models (GEC, EC, etc.)

## References

- PyTorch docs: `.item()` triggers CPU sync and blocks until tensor value is available

---

## 2025-11-09 to 2025-11-10: False Diagnosis - Cutoff EMA Sync

**Status**: RESOLVED (misdiagnosed - actual cause was metric pipeline)
**What happened**: Multi-GPU deadlocks observed during `step_complete()` were incorrectly attributed to cutoff EMA synchronization

### Resolution (2025-11-10)

After fixing the metric pipeline refactoring (ModelBase converts tensors to Python types), ran comprehensive tests:

**Test 1: Single-GPU with capacity threshold**
```bash
CUDA_VISIBLE_DEVICES=0 python train.py mlp=gec_shared_capacity +experiment=debug \
  training.max_steps=6 training.threshold_warmup_steps=3
```
✅ Passed - No issues

**Test 2: Multi-GPU with capacity threshold + threshold mode active**
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 train.py mlp=gec_shared_capacity \
  +experiment=debug training.max_steps=6 training.threshold_warmup_steps=3
```
✅ Passed - No deadlocks, switched to threshold at step 3, completed successfully

**Actual root cause**: The deadlock was NOT the cutoff EMA sync. It was the metric pipeline returning tensors that eventually reached rank-divergent logger code. The cutoff EMA sync (`model_base.py:596-647`) was implemented correctly:
- Batched `all_gather_object` for all blocks
- CPU FP32 conversion
- Explicit barrier
- Proper averaging and copy-back

**Key learning**: Deadlocks during `step_complete()` can be caused by issues earlier in the pipeline (metrics), not necessarily the sync logic itself. Always test thoroughly before concluding root cause.

**Debugging timeline archived**: Complete debugging journey (2025-11-07 to 2025-11-10) including false hypotheses, proposed fixes, and timeline available in `memory/archive/debugging/cutoff_ema_sync_false_diagnosis.md`

---

## 2025-11-05: Logger Deadlock - Tensor Operations in Logging Path

**Status**: Fixed
**Severity**: Critical (deadlocks multi-GPU training at first logging step)

### Symptoms
- Multi-GPU training hangs at step 0 during first logging interval
- Rank 0 enters logging code and never exits
- Rank 1 waits at barrier indefinitely
- No error messages, silent hang

### Root Cause

**Location**: `src/utils/logger.py:109, 116`

Logger performed tensor operations (`.numel()`, `.tolist()`) on GPU tensors during metric formatting:

```python
# BAD: Keep vector tensors on GPU
flat_metrics[formatted_key] = value  # value is still GPU tensor

# BAD: Call .numel() on GPU tensors during filtering
scalar_metrics = {k: v for k, v in flat_metrics.items()
                  if not hasattr(v, 'numel') or v.numel() == 1}
```

**Why this deadlocks**:
1. Rank 0 enters logging block (master_process only)
2. Logger calls `.numel()` on GPU tensors → triggers CUDA sync
3. If any pending DDP operations from rank 1, sync blocks waiting
4. Rank 1 waiting at barrier after logging block
5. Deadlock!

### The Fix

**Fix 1: Convert All Tensors to Python Types Immediately**

```python
# GOOD: Convert vector tensors to Python lists
if value.numel() == 1:
    flat_metrics[formatted_key] = value.item()
else:
    flat_metrics[formatted_key] = value.detach().cpu().tolist()
```

**Fix 2: Use Python Type Checking Instead of Tensor Operations**

```python
# GOOD: Check Python types, no tensor operations
scalar_metrics = {k: v for k, v in flat_metrics.items()
                  if isinstance(v, (int, float))}
```

**Files changed**:
- `src/utils/logger.py:109` - Convert vector tensors to lists
- `src/utils/logger.py:116` - Use `isinstance()` instead of `.numel()`
- `train.py:314` - Convert `grad_norm` tensor to float before logging

### Key Insights

1. **Logger must never touch GPU tensors**: All metrics should be Python types (float, int, list) before entering logger
2. **Even "safe" tensor operations can deadlock**: `.numel()` is a metadata operation but still triggers CUDA sync
3. **Logging is rank-divergent**: Only rank 0 logs, so any sync operation in logger creates mismatch
4. **Pre-convert in training loop**: Convert tensors to Python types before passing to logger

### Prevention Guidelines

**In logging code**:
- ✅ Only accept Python types (float, int, list, dict)
- ❌ Never call tensor methods (`.item()`, `.numel()`, `.tolist()`)
- ❌ Never use `hasattr(v, 'numel')` checks on values from logger args

**In training loop**:
- ✅ Convert ALL tensor metrics to Python types before logging
- ✅ Use `.detach().cpu()` before `.item()` or `.tolist()`
- ✅ Handle both scalars and vectors explicitly

### Testing

Verified with 2-GPU training:
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 \
  train.py +experiment=debug mlp=gec_shared \
  model_size=tiny training.max_steps=10
```

Training now completes without deadlock at logging steps.

---

## 2025-11-10: Metric Pipeline Refactoring - Structural Deadlock Prevention

**Status**: Implemented
**Severity**: Architectural improvement (makes deadlocks structurally impossible)

### Motivation

While previous fixes addressed specific `.item()` deadlock instances, they relied on developer discipline. Each new metric or logging path risked reintroducing the bug. The solution: **move tensor→scalar conversion into ModelBase**, ensuring the training loop only handles Python types.

### Design Philosophy

**Enforce separation via API boundaries**, not code review:

```
GPU Zone (tensors) → Conversion Boundary → CPU Zone (Python types)
      ↓                      ↓                        ↓
  ModelBase             _metrics_to_scalars()    train.py + Logger
  (computes)             (converts once)          (logs safely)
```

**Key invariant**: `ModelOutput.metrics` always contains Python types (float/list), never tensors.

### Implementation

#### 1. ModelBase: Convert in forward()

**Location**: `src/models/model_base.py:748-781`

```python
@staticmethod
def _metrics_to_scalars(metrics: dict) -> dict:
    """
    Convert tensor metrics to Python types.

    CRITICAL: This prevents distributed deadlocks by ensuring tensors
    never reach rank-divergent code in the training loop.
    """
    result = {}
    for k, v in metrics.items():
        assert torch.is_tensor(v), f"Metric '{k}' is not a tensor (got {type(v)})"
        v_cpu = v.detach().cpu()
        if v_cpu.numel() == 1:
            result[k] = float(v_cpu.item())
        else:
            result[k] = v_cpu.tolist()
    return result

# In forward():
scalar_metrics = self._metrics_to_scalars(aggregated_metrics)
assert not any(torch.is_tensor(v) for v in scalar_metrics.values())
return ModelOutput(loss=loss, logits=logits, metrics=scalar_metrics)
```

#### 2. Training Loop: Pure Python Arithmetic

**Location**: `train.py:227-268`

```python
# Old: Tensor accumulation with detach/clone
v_detached = v.detach().clone()
routing_metrics[k] = routing_metrics[k] + v_detached / grad_accum_steps

# New: Simple Python arithmetic
for k, v in output.metrics.items():
    assert not torch.is_tensor(v), "Passing tensor-type metrics risks deadlocks"

    if isinstance(v, list):
        routing_metrics[k] = [acc + val/grad_accum_steps
                             for acc, val in zip(routing_metrics[k], v)]
    else:
        routing_metrics[k] += v / grad_accum_steps
```

**Removed**: Manual tensor→scalar conversion (old lines 278-291)

#### 3. Logger: Strict Type Validation

**Location**: `src/utils/logger.py:90-101`

```python
# Assert: No tensors allowed (defense in depth)
for key, value in metrics.items():
    assert not torch.is_tensor(value), \
        f"Tensor metric '{key}' passed to logger! " \
        f"Passing tensor-type metrics risks deadlocks."

    assert isinstance(value, (int, float, list, bool)), \
        f"Unexpected metric type for '{key}': {type(value)}"
```

**Removed**: Fallback tensor handling code (lines 96-104)

#### 4. Routing Metrics: Assert Tensor Outputs

**Location**: `src/utils/routing_metrics.py:193-197`

```python
# Assert: All outputs are tensors (ModelBase will convert)
for k, v in metrics.items():
    assert torch.is_tensor(v), \
        f"compute_routing_metrics() should return tensors, got {type(v)} for '{k}'"
```

### Benefits

1. **Deadlocks structurally impossible**: Tensors cannot reach rank-divergent code
2. **Simpler training loop**: No tensor handling, just dict arithmetic
3. **Defense in depth**: Assertions at every boundary catch bugs immediately
4. **Better performance**:
   - Barriers moved inside logging conditional (only on logging steps)
   - Evaluation now rank-0 only (efficiency)
5. **Clear separation**: Model owns conversion, training loop just computes

### Testing

**Single-GPU**:
```bash
CUDA_VISIBLE_DEVICES=0 python train.py +experiment=debug training.max_steps=3
```
✅ Passed

**Multi-GPU**:
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 train.py +experiment=debug training.max_steps=3
```
✅ Passed - No deadlocks, all assertions passed

### Files Changed

1. `src/models/model_base.py`: Added `_metrics_to_scalars()`, convert in `forward()`
2. `train.py`: Removed manual conversion, simplified accumulation, added assertions
3. `src/utils/logger.py`: Removed tensor handling, added strict assertions
4. `src/utils/routing_metrics.py`: Added tensor output assertion

### Prevention Guidelines

**For future development**:
- ✅ `ModelOutput.metrics` always contains Python types
- ✅ Training loop accumulates scalars/lists
- ✅ Logger rejects tensors immediately
- ❌ Never pass tensors to logger
- ❌ Never add tensor operations to training loop metric handling

**Error messages are explicit**: "Passing tensor-type metrics risks deadlocks"

### References

- Design document: `memory/design/metric_logging_architecture.md`
- Related: Logger deadlock fix (2025-11-05), Forward pass .item() fix (2025-11-05)
