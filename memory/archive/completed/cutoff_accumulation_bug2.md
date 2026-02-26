# Bug 2: DDP Cutoff Divergence + Micro-Batch Inconsistency

**Date**: 2025-11-04
**Status**: Active during multi-GPU training with threshold routing
**Severity**: HIGH (affects training consistency)

## The Problem

### Issue 1: Inconsistent Routing Within a Single Step

During gradient accumulation (e.g., `grad_accum_steps=4`), cutoffs change between micro-batches:

```python
# Current buggy behavior at step 1001
for micro_step in range(4):
    # Micro-step 0: uses cutoffs [1.850, 2.300, 2.050]
    # Micro-step 1: uses cutoffs [1.8525, 2.302, 2.0515]  ← Changed!
    # Micro-step 2: uses cutoffs [1.85345, ...]           ← Changed again!
    # Micro-step 3: uses cutoffs [1.856, ...]             ← Different again!
    output = model(x, y)  # Updates EMA during forward
    loss.backward()
```

**Why this is bad**: Gradient accumulation should simulate one large batch, but different micro-batches see different routing → breaks this semantics.

### Issue 2: DDP Divergence

Each GPU maintains separate cutoff EMAs. Without sync:
- GPU-0 sees its own batches → cutoffs drift toward GPU-0's data distribution
- GPU-1 sees its own batches → cutoffs drift toward GPU-1's data distribution
- By step 1000, cutoffs have significantly diverged

## Requirements (From User)

1. **Within one step**: Cutoffs must be frozen across all micro-batches
2. **Accumulation**: Use arithmetic average (not EMA) of topk stats within a step
3. **After step**: Update EMA once with the averaged stats
4. **Only threshold mode**: Keep current behavior during warmup (topk routing)
5. **DDP strategy**:
   - No sync during warmup (steps 0-999)
   - Sync after each step in threshold mode (steps >= 1000)
6. **Dual-path**: Keep computing topk for EMA updates (even during threshold routing)

## Current Code Flow

### train.py (lines 217-253)

```python
# No preparation before micro-steps

for micro_step in range(grad_accum_steps):
    output = model(x, y)  # ← EMA updated HERE (inside forward)
    loss = output["loss"]
    grad_scaler.scale(loss / grad_accum_steps).backward()

# After all micro-steps
if ddp and step >= threshold_warmup_steps:
    orig_model.sync_cutoff_ema()  # ← Sync happens AFTER
```

### GECSharedMLPCapacityThreshold.forward_threshold() (lines 82-97)

```python
if self.training:  # Dual-path: compute topk for EMA
    with torch.no_grad():
        topk_values, _ = torch.topk(router_logits_flat.t(), k=k_target, dim=1)
        cutoffs = topk_values[:, -1]

        # Update EMA immediately (EVERY micro-step!)
        self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
        self.cutoff_ema_count += 1
```

## Proposed Solution

### High-Level Algorithm

```python
# Before micro-steps (threshold mode only)
orig_model.start_cutoff_accumulation()  # Freeze cutoffs, enable accumulator

for micro_step in range(grad_accum_steps):
    output = model(x, y)  # Uses frozen cutoffs, accumulates topk stats
    loss.backward()

# After all micro-steps (threshold mode only)
orig_model.finalize_cutoff_ema()  # Compute average, update EMA

# Sync for DDP (threshold mode only)
if ddp and step >= threshold_warmup_steps:
    orig_model.sync_cutoff_ema()
```

### Implementation Details

#### 1. Add Accumulator State to MLP Classes

**Files to modify**:
- `src/models/gec_shared/shared_capacity_threshold.py` (GECSharedMLPCapacityThreshold)
- `src/models/gec_shared/shared.py` (GECSharedMLP - parent class)

**New state variables**:
```python
def __init__(self, config):
    # ... existing init ...

    # Cutoff accumulation for gradient accumulation
    self.accumulation_enabled = False
    self.cutoff_accumulator = None  # Will be [n_routed_experts, n_accumulations]
    self.accumulation_count = 0
```

#### 2. Modify forward_threshold() to Support Accumulation

**Location**: Both classes above

**Current code** (lines 82-97 in shared_capacity_threshold.py):
```python
if self.training:
    with torch.no_grad():
        topk_values, _ = torch.topk(router_logits_flat.t(), k=k_target, dim=1)
        cutoffs = topk_values[:, -1]  # [n_routed_experts]

        # Update EMA
        self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
        self.cutoff_ema_count += 1
```

**New code**:
```python
if self.training:
    with torch.no_grad():
        topk_values, _ = torch.topk(router_logits_flat.t(), k=k_target, dim=1)
        cutoffs = topk_values[:, -1]  # [n_routed_experts]

        if self.accumulation_enabled:
            # Accumulate for later averaging
            if self.cutoff_accumulator is None:
                # Initialize accumulator (can't know size until first forward)
                self.cutoff_accumulator = cutoffs.unsqueeze(1)  # [E, 1]
            else:
                self.cutoff_accumulator = torch.cat([
                    self.cutoff_accumulator,
                    cutoffs.unsqueeze(1)
                ], dim=1)  # [E, n_accumulations]
            self.accumulation_count += 1
        else:
            # Update EMA immediately (backward compatibility)
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
            self.cutoff_ema_count += 1
```

#### 3. Add Methods to BaseGPT

**File**: `src/models/model_base.py`

**Method 1: start_cutoff_accumulation()**
```python
def start_cutoff_accumulation(self):
    """
    Enable cutoff accumulation mode for gradient accumulation.

    During accumulation:
    - Cutoffs are frozen (self.cutoff_ema not updated)
    - Topk statistics are accumulated for later averaging

    Call this before micro-steps in threshold routing mode.
    """
    for block in self.blocks:
        if hasattr(block.mlp, 'accumulation_enabled'):
            block.mlp.accumulation_enabled = True
            block.mlp.cutoff_accumulator = None  # Reset
            block.mlp.accumulation_count = 0
```

**Method 2: finalize_cutoff_ema()**
```python
def finalize_cutoff_ema(self):
    """
    Finalize cutoff accumulation: compute average and update EMA.

    Computes arithmetic mean of accumulated topk cutoffs, then
    updates EMA using this mean (not the individual samples).

    Call this after all micro-steps complete.
    """
    for block in self.blocks:
        mlp = block.mlp
        if hasattr(mlp, 'accumulation_enabled') and mlp.accumulation_enabled:
            if mlp.cutoff_accumulator is not None and mlp.accumulation_count > 0:
                # Compute arithmetic mean across accumulations
                avg_cutoffs = mlp.cutoff_accumulator.mean(dim=1)  # [n_routed_experts]

                # Update EMA with averaged cutoffs
                mlp.cutoff_ema = mlp.ema_decay * mlp.cutoff_ema + (1 - mlp.ema_decay) * avg_cutoffs
                mlp.cutoff_ema_count += 1

            # Disable accumulation mode
            mlp.accumulation_enabled = False
            mlp.cutoff_accumulator = None
            mlp.accumulation_count = 0
```

**Method 3: Modify existing sync_cutoff_ema()** (optional improvement)

Current implementation syncs both `cutoff_ema` and `cutoff_ema_count`. The count sync might not be necessary, but keeping it shouldn't hurt.

#### 4. Update train.py

**Current code** (lines 217-253):
```python
for micro_step in range(grad_accum_steps):
    with autocast_ctx:
        output = model(x, y)
        loss = output["loss"]
    grad_scaler.scale(loss / grad_accum_steps).backward()

# ... optimizer step ...

if ddp and step >= threshold_warmup_steps:
    orig_model.sync_cutoff_ema()
```

**New code**:
```python
# Before micro-steps: enable accumulation if in threshold mode
in_threshold_mode = (config.training.threshold_warmup_steps >= 0 and
                     step >= config.training.threshold_warmup_steps)

if in_threshold_mode:
    orig_model.start_cutoff_accumulation()

for micro_step in range(grad_accum_steps):
    with autocast_ctx:
        output = model(x, y)
        loss = output["loss"]
    grad_scaler.scale(loss / grad_accum_steps).backward()

# After micro-steps: finalize accumulation
if in_threshold_mode:
    orig_model.finalize_cutoff_ema()

# ... optimizer step ...

# Sync after finalization (threshold mode only)
if ddp and in_threshold_mode:
    orig_model.sync_cutoff_ema()
```

**Also remove redundant sync at mode switch** (line 212):
```python
# OLD (remove this)
if ddp:
    orig_model.sync_cutoff_ema()

# NEW (just set mode, sync will happen at end of step 1000)
# No sync needed here
```

## Expected Behavior After Fix

### Step 1001 (First Threshold Step)

**Before micro-steps**:
- All GPUs have synced cutoffs: `[1.850, 2.300, 2.050]` (from step 1000 finalization)
- `start_cutoff_accumulation()` called → accumulation_enabled = True

**Micro-step 0**:
- GPU-0: Routes with `[1.850, 2.300, 2.050]`, computes topk → `[2.1, 2.5, 2.2]`
- GPU-0: Accumulates (doesn't update EMA)
- GPU-1: Routes with `[1.850, 2.300, 2.050]` (SAME!), computes topk → `[1.7, 2.1, 1.9]`
- GPU-1: Accumulates

**Micro-step 1**:
- GPU-0: Still routes with `[1.850, 2.300, 2.050]` (FROZEN!), topk → `[2.0, 2.4, 2.1]`
- GPU-0: Accumulates
- GPU-1: Still routes with `[1.850, 2.300, 2.050]` (FROZEN!), topk → `[1.8, 2.2, 2.0]`
- GPU-1: Accumulates

**Micro-step 2, 3**: Same pattern (frozen cutoffs)

**After micro-steps**:
- `finalize_cutoff_ema()` called
- GPU-0: avg = mean([[2.1, 2.0, ...], [2.5, 2.4, ...], ...]) = `[2.05, 2.45, 2.15]`
- GPU-0: EMA update: `0.99 * [1.850, 2.300, 2.050] + 0.01 * [2.05, 2.45, 2.15] = [1.8525, 2.3015, 2.0515]`
- GPU-1: avg = `[1.75, 2.15, 1.95]`
- GPU-1: EMA update: `0.99 * [1.850, 2.300, 2.050] + 0.01 * [1.75, 2.15, 1.95] = [1.8485, 2.2985, 2.0485]`

**After sync**:
- Both GPUs: `([1.8525, ...] + [1.8485, ...]) / 2 = [1.8505, 2.3000, 2.0500]`

**Step 1002**: Starts with synced `[1.8505, 2.3000, 2.0500]`

## Testing Plan

### Test 1: Single GPU, No Accumulation (Backward Compat)

**Config**: `grad_accum_steps=1`, single GPU
**Expected**: Behaves exactly like before (accumulation code not triggered)

### Test 2: Single GPU, With Accumulation

**Config**: `grad_accum_steps=4`, single GPU
**Verify**:
1. Cutoffs stay frozen during all 4 micro-steps
2. EMA updated once after step
3. Routing decisions consistent across micro-steps

**How to verify**: Add debug logging:
```python
# In forward_threshold(), log cutoff_ema before routing
print(f"Step {step}, micro {micro_step}: cutoff_ema = {self.cutoff_ema}")
```

### Test 3: Multi-GPU, With Accumulation

**Config**: 2 GPUs, `grad_accum_steps=4`
**Verify**:
1. Both GPUs use same cutoffs during micro-steps
2. Both GPUs have same cutoffs after sync
3. Training doesn't crash

**How to verify**: Print cutoffs on both ranks:
```python
print(f"Rank {rank}, step {step}: cutoff_ema after sync = {mlp.cutoff_ema}")
```

### Test 4: Warmup Behavior Unchanged

**Config**: Steps 0-999 (warmup)
**Verify**:
1. Accumulation NOT enabled (should update EMA each micro-step as before)
2. No sync during warmup
3. At step 1000, sync happens and cutoffs averaged

## Open Questions / Concerns

### Q1: Memory Overhead

Accumulating cutoffs requires storing `[n_routed_experts, grad_accum_steps]` tensors.

**Example**:
- 8 experts, 4 micro-steps → 32 floats per layer
- 12 layers → 384 floats total
- Negligible!

### Q2: Performance Overhead

Extra operations:
1. `torch.cat()` during accumulation (4x per step per layer)
2. `.mean(dim=1)` during finalization (1x per step per layer)

**Impact**: Negligible compared to forward/backward pass.

### Q3: Edge Cases

**What if grad_accum_steps=1?**
- Accumulation never grows beyond size 1
- Mean of 1 element = the element itself
- EMA update same as before ✓

**What if no micro-steps complete?** (e.g., crash mid-step)
- Accumulator gets reset at next `start_cutoff_accumulation()`
- No stale data ✓

**What if warmup_steps < 0?** (disabled)
- `in_threshold_mode` always False
- Accumulation never enabled
- Behaves like normal topk routing ✓

### Q4: Interaction with Compilation

**Does torch.compile support this?**
- Dynamic tensor sizes (accumulator grows each micro-step)
- Might trigger recompilation each micro-step? 🤔

**Mitigation**: Pre-allocate accumulator with fixed size:
```python
# Instead of torch.cat(), use indexing:
self.cutoff_accumulator = torch.zeros(
    n_routed_experts,
    grad_accum_steps,  # Fixed size!
    device=cutoffs.device
)
self.cutoff_accumulator[:, self.accumulation_count] = cutoffs
```

**But**: Need to pass `grad_accum_steps` to MLP classes. More intrusive change.

**Decision**: Start with torch.cat(), optimize if profiling shows issue.

## Alternative Designs Considered

### Alt 1: Accumulate in train.py (Not in MLP)

**Idea**: Have MLP return cutoffs, accumulate in train loop:

```python
all_cutoffs = []
for micro_step in range(grad_accum_steps):
    output = model(x, y, return_cutoffs=True)
    all_cutoffs.append(output['cutoffs'])

avg_cutoffs = torch.stack(all_cutoffs).mean(dim=0)
model.update_cutoff_ema(avg_cutoffs)
```

**Pros**: Cleaner separation, train.py controls accumulation
**Cons**: MLP API change (return cutoffs), need to thread through all layers

### Alt 2: Context Manager

```python
with model.accumulate_cutoffs():
    for micro_step in range(grad_accum_steps):
        output = model(x, y)
        loss.backward()
# EMA updated on context exit
```

**Pros**: Pythonic, clear scope
**Cons**: Harder to implement (need __enter__/__exit__)

### Alt 3: Callback System

**Pros**: Very flexible
**Cons**: Over-engineered for this use case

**Decision**: Go with explicit start/finalize methods (proposed solution).

## Implementation Order

1. **Add accumulator state** to both MLP classes
2. **Modify forward_threshold()** with accumulation logic
3. **Add methods to BaseGPT** (start/finalize)
4. **Update train.py** to call start/finalize
5. **Remove redundant sync** at mode switch
6. **Test** with debug experiment

## Success Criteria

✅ Training doesn't crash with threshold routing + grad accumulation
✅ All micro-steps use identical cutoffs within one step
✅ Multi-GPU training has synced cutoffs across GPUs
✅ Warmup behavior unchanged (backward compatible)
✅ Single-GPU, no-accumulation behavior unchanged (backward compatible)
