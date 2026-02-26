# Bug 4: Metrics Aggregation TypeError

**Date**: 2025-11-04
**Status**: ✅ RESOLVED (2025-11-04)
**Severity**: CRITICAL (was blocking training)

## Resolution

**Root Cause**: `.item()` was incorrectly used on metric tensors, converting them to Python floats which cannot be aggregated with `torch.stack()`.

**Investigation Finding**: `.item()` was NOT needed for gradient detachment - metrics are already computed from non-differentiable operations (boolean masks, `torch.zeros()`) so they have `requires_grad=False` by default.

**Fix Applied**:
1. Removed `.item()` from all tensor metrics in:
   - `src/models/gec_shared/shared_capacity_threshold.py:232,234,235,253,254`
   - `src/models/gec_shared/shared.py:370,372,373`
   - `src/models/gec_shared/shared_trainable_threshold.py:185,187,188`

2. Wrapped Python int divisions in `torch.tensor()`:
   - `src/models/gec_shared/shared_capacity_threshold.py:241-248` (capacity metrics)

**Why This Works**:
- Metrics already have no gradients (no `.detach()` needed)
- Logging layer (`train.py`, `logger.py`) handles tensor→float conversion
- Matches existing pattern in `src/utils/routing_metrics.py`

**Verified**: Training with `mlp=gec_shared_capacity` completes successfully ✅

---

## The Error

```python
File "/data2/hanchi/nano_gec/src/models/model_base.py", line 672, in forward
    aggregated_metrics[k] = torch.stack(v_list).mean()
                            ^^^^^^^^^^^^^^^^^^^
TypeError: expected Tensor as element 0 in argument 0, but got float
```

## Context

**Triggered by**: Training with `mlp=gec_shared_capacity`, `threshold_warmup_steps=50`, `expert_capacity_factor=0.2`

**Why it happens now**:
- `GECSharedMLPCapacityThreshold` runs threshold routing during training
- Threshold routing with capacity constraints returns float metrics
- Aggregation code expects all metrics to be tensors

## Root Cause Analysis

### The Aggregation Code (model_base.py:662-672)

```python
def forward(self, x, targets=None):
    # ... forward through blocks ...

    # Each block returns metrics dict
    # Aggregate metrics across all blocks
    aggregated_metrics = {}
    metrics_by_key = {}
    for block_metrics in all_block_metrics:
        for k, v in block_metrics.items():
            if k not in metrics_by_key:
                metrics_by_key[k] = []
            metrics_by_key[k].append(v)  # ← Appends floats or tensors

    for k, v_list in metrics_by_key.items():
        aggregated_metrics[k] = torch.stack(v_list).mean()  # ← CRASHES if v_list contains floats
```

**Assumption**: All metrics are tensors.

### Where Floats Come From

**File**: `src/models/gec_shared/shared_capacity_threshold.py`

**Category 1: Always present (lines 232-235)**
```python
'gec_shared_avg_experts_per_token': token_fanout_with_shared.mean().item(),  # ← .item() returns float
'gec_shared_max_experts_per_token': token_fanout_with_shared.max().item(),
'gec_shared_min_experts_per_token': token_fanout_with_shared.min().item(),
```

**Category 2: Capacity-specific (lines 241-248)**
```python
metrics['capacity_hit_rate'] = (capacity_overflow + capacity_underflow) / n_routed_experts  # ← Python division = float
metrics['capacity_overflow_rate'] = capacity_overflow / n_routed_experts
metrics['capacity_underflow_rate'] = capacity_underflow / n_routed_experts
metrics['raw_mean'] = raw_k_tensor.mean().item()  # ← .item()
metrics['raw_std'] = raw_k_tensor.std().item()
```

**Same pattern in**:
- `src/models/gec_shared/shared.py:370-373`
- `src/models/gec_shared/shared_trainable_threshold.py:185-188`

## Proposed Solution (WITH HESITATIONS)

### Simple Fix: Remove `.item()`, Wrap Python Divisions

```python
# Category 1: Remove .item()
'gec_shared_avg_experts_per_token': token_fanout_with_shared.mean(),  # Keep as tensor

# Category 2: Wrap divisions
metrics['capacity_hit_rate'] = torch.tensor(
    (capacity_overflow + capacity_underflow) / n_routed_experts,
    device=x.device,
    dtype=torch.float32
)
```

### ⚠️ HESITATION 1: Why Was `.item()` Used?

**Possible reasons**:
1. **WandB logging**: Maybe floats are needed for logging?
   - **Counter**: WandB accepts both floats and tensors (converts tensors to floats automatically)

2. **Memory efficiency**: Keeping tensors in metrics dict wastes memory?
   - **Counter**: These are scalar tensors (1 element), negligible overhead

3. **Original code didn't aggregate**: Maybe metrics were only logged, not aggregated?
   - **Need to check**: When was aggregation added? Was it after these metrics?

### ⚠️ HESITATION 2: Should All Metrics Be Aggregated?

**Current behavior**: Aggregates ALL metrics across ALL blocks (layers).

**Questions**:
1. Does averaging `capacity_hit_rate` across layers make sense?
   - Each layer has different expert activation patterns
   - Layer-0 might have 0% capacity hits, Layer-11 might have 50%
   - **Average might be meaningless**

2. Should some metrics be layer-specific instead?
   - Maybe log `layer_{i}_capacity_hit_rate` for each layer?
   - Or just log layer-0, layer-mid, layer-last?

3. Are there metrics that should be summed, not averaged?
   - `capacity_overflow` counts across layers → sum makes more sense?

### ⚠️ HESITATION 3: Different Aggregation Strategies

**Current**: All metrics use `mean()` aggregation.

**Alternatives**:
```python
# Option A: Different strategies per metric type
if k.endswith('_rate'):
    aggregated_metrics[k] = torch.stack(v_list).mean()  # Rates → average
elif k.endswith('_count'):
    aggregated_metrics[k] = torch.stack(v_list).sum()   # Counts → sum
elif k.startswith('max_'):
    aggregated_metrics[k] = torch.stack(v_list).max()   # Max → max across layers
```

**But this requires**: Redesigning the metrics system, not just a bug fix.

### ⚠️ HESITATION 4: Type System Issues

**Problem**: The aggregation code doesn't know which metrics are aggregatable.

**Example**:
- `loss`: Should be averaged ✓
- `capacity_hit_rate`: Maybe averaged? 🤔
- `router_logits_histogram`: Can't be aggregated at all! ✗

**Current code**: Blindly aggregates everything, assumes all are tensors.

**Better design**:
```python
# Metrics dict with metadata
metrics = {
    'loss': {'value': tensor, 'aggregation': 'mean'},
    'capacity_hit_rate': {'value': tensor, 'aggregation': 'mean'},
    'layer_id': {'value': tensor, 'aggregation': 'none'},  # Don't aggregate
}
```

**But**: This is a major refactor, not a quick fix.

### ⚠️ HESITATION 5: Other Code Might Depend on Floats

**Risk**: Other parts of the codebase might expect floats.

**Need to check**:
1. Logging code (train.py) - does it handle tensors?
2. WandB integration - does it auto-convert tensors?
3. Checkpointing - are metrics saved? Do they need to be floats?

**Mitigation**: Keep types as tensors internally, convert to floats at logging time.

## Recommended Approach

### Minimal Fix (Unblock Training)

1. **Remove `.item()` from all metrics** in:
   - `shared_capacity_threshold.py:232-235, 244-248`
   - `shared.py:370-373`
   - `shared_trainable_threshold.py:185-188`

2. **Wrap Python divisions in `torch.tensor()`**:
   ```python
   metrics['capacity_hit_rate'] = torch.tensor(
       (capacity_overflow + capacity_underflow) / n_routed_experts,
       device=x.device
   )
   ```

3. **Test immediately**: Verify training doesn't crash.

4. **Check logging**: Verify WandB/print statements handle tensors.

### Follow-up Investigation

1. **Why was `.item()` added?**
   - Check git history
   - Ask original author intent

2. **Should metrics be aggregated?**
   - Review which metrics make sense to average across layers
   - Consider layer-specific logging instead

3. **Type system for metrics**
   - Design metadata system for aggregation strategies
   - Separate aggregatable vs non-aggregatable metrics

## Alternative Solutions

### Alt 1: Fix Aggregation Code (Not Metrics)

Instead of changing metrics to tensors, make aggregation handle both:

```python
for k, v_list in metrics_by_key.items():
    # Convert all to tensors if mixed types
    tensor_list = [v if isinstance(v, torch.Tensor) else torch.tensor(v, device=device)
                   for v in v_list]
    aggregated_metrics[k] = torch.stack(tensor_list).mean()
```

**Pros**: No changes to metric-returning code
**Cons**: Hides the type inconsistency, might mask other bugs

### Alt 2: Separate Float and Tensor Metrics

```python
# Return two dicts
return {
    'tensor_metrics': {...},  # Aggregatable tensors
    'scalar_metrics': {...},  # Python floats for logging only
}
```

**Pros**: Clear separation of concerns
**Cons**: Requires API changes across all MLP classes

### Alt 3: Don't Aggregate Certain Metrics

```python
# Whitelist of aggregatable metrics
AGGREGATABLE_METRICS = {'loss', 'router_entropy', ...}

for k, v_list in metrics_by_key.items():
    if k in AGGREGATABLE_METRICS:
        aggregated_metrics[k] = torch.stack(v_list).mean()
    else:
        aggregated_metrics[k] = v_list[0]  # Just use first layer
```

**Pros**: Explicit control over what gets aggregated
**Cons**: Maintenance burden (update whitelist when adding metrics)

## Open Questions

1. **What is the intended behavior?** Should capacity metrics be averaged across layers?

2. **Why the type inconsistency?** Was `.item()` added before aggregation existed?

3. **Should we aggregate at all?** Maybe log per-layer metrics instead of averaging?

4. **What about validation/test metrics?** Same issue might exist in eval mode.

5. **Performance impact?** Keeping tensors vs floats - does it matter?

## Testing Plan

After applying fix:

1. **Smoke test**: Run training with `+experiment=debug` for 10 steps
2. **Check logs**: Verify WandB receives metrics correctly
3. **Multi-GPU**: Test DDP doesn't crash on metric aggregation
4. **Eval mode**: Test validation also works (might have same bug)
5. **Different configs**: Test with/without capacity constraints

## Conclusion

**Immediate action**: Remove `.item()` and wrap divisions (minimal fix).

**But**: This bug reveals deeper design questions about:
- What should be aggregated vs logged per-layer
- Type safety in metrics system
- Aggregation strategies (mean vs sum vs max)

**Recommend**:
1. Fix now to unblock training
2. Open separate issue to redesign metrics system
3. Document intended semantics for each metric
