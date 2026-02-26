# Cutoff Accumulation Implementation Plan (Bug 2)

**Status**: ✅ IMPLEMENTED - Archived 2025-11-04
**Design Extracted To**:
- `memory/design/cutoff_accumulation.md` (step-boundary pattern, architecture)
- `memory/design/threshold_routing_design.md` (distributed training, separation of concerns)

**Date**: 2025-11-04
**Related Bug**: Bug 2 - DDP cutoff divergence + micro-batch inconsistency

## Executive Summary

**Problem**: During threshold routing with gradient accumulation, cutoffs change between micro-batches, breaking the semantics of gradient accumulation. Additionally, in DDP training, each GPU maintains separate EMAs that diverge without synchronization.

**Solution**: Introduce a "step-boundary pattern" where cutoffs are frozen during micro-batches, accumulated statistics are averaged, and EMA is updated once per training step. A new `step_complete()` method encapsulates all step-boundary operations.

**Key Design Decision**: Use `step_complete()` as the abstraction for "end of training step" operations, rather than overloading existing methods like `sync_cutoff_ema()`.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Detailed Design](#detailed-design)
3. [Implementation Details](#implementation-details)
4. [Migration Guide](#migration-guide)
5. [Testing Strategy](#testing-strategy)
6. [Edge Cases](#edge-cases)
7. [Performance Considerations](#performance-considerations)
8. [Future Extensions](#future-extensions)

---

## Design Philosophy

### Core Principles

1. **Step-boundary pattern**: Training steps are the fundamental unit. State updates happen at step boundaries, not during forward passes.

2. **Separation of concerns**:
   - Forward pass: Computes outputs, accumulates statistics
   - Step boundary: Finalizes accumulated statistics, updates training state
   - BaseGPT: Coordinates across layers
   - MLP classes: Implement domain logic

3. **Explicit over implicit**: Rather than hiding finalization in `sync_cutoff_ema()`, make it explicit with `step_complete()`.

4. **Works for all cases**: Single GPU, multi-GPU, any gradient accumulation steps.

### Design Alternatives Considered

#### Alternative 1: Overload sync_cutoff_ema()
**Rejected** because:
- Name doesn't reflect finalization behavior
- Confusing on single GPU (what are we syncing?)
- Hidden side effects

#### Alternative 2: Multiple explicit methods
```python
model.finalize_accumulation()
model.update_cutoff_ema()
model.sync_cutoff_ema()
```
**Rejected** because:
- Creates artificial boundaries
- Easy to call in wrong order
- Three calls instead of one

#### Alternative 3: Context manager
```python
with model.accumulate_cutoffs():
    for micro_step in ...:
        model(x, y)
```
**Rejected** because:
- More complex implementation
- Unclear interaction with torch.compile
- Less explicit about when EMA updates

#### Chosen: step_complete()
- Clear name and intent
- Single call handles everything
- Natural extension point for future step-boundary operations

---

## Detailed Design

### High-Level Flow

```
Training Step N:
  ┌─────────────────────────────────────────────┐
  │ Micro-batch 0                               │
  │   forward() → accumulates cutoffs           │
  │   backward()                                │
  ├─────────────────────────────────────────────┤
  │ Micro-batch 1                               │
  │   forward() → accumulates cutoffs (frozen!) │
  │   backward()                                │
  ├─────────────────────────────────────────────┤
  │ ... (more micro-batches) ...                │
  ├─────────────────────────────────────────────┤
  │ optimizer.step()                            │
  ├─────────────────────────────────────────────┤
  │ step_complete()                             │
  │   └─> finalize_cutoff_accumulation()        │
  │         └─> compute arithmetic mean         │
  │         └─> update EMA                      │
  │         └─> clear accumulator               │
  │   └─> sync across GPUs (if DDP)             │
  └─────────────────────────────────────────────┘
```

### Behavior By Routing Mode

#### During Warmup (Steps 0-999, Topk Routing)

**Current behavior** (unchanged):
- `forward_topk()` computes topk cutoffs
- Updates EMA immediately inside forward
- No accumulation
- No sync (per requirements)

**Why unchanged**: User requirement specifies no sync during warmup.

#### During Threshold Mode (Steps >= 1000)

**New behavior**:
- `forward_threshold()` computes topk cutoffs (dual-path)
- **Accumulates** cutoffs in list, does NOT update EMA
- All micro-batches use frozen `cutoff_ema` from previous step
- After all micro-batches: `step_complete()` called
  - Computes arithmetic mean of accumulated cutoffs
  - Updates EMA once with this mean
  - Syncs across GPUs

### State Transitions

```
Step 999 (Last Warmup):
  cutoff_ema = [2.5, 3.1, 2.8]  (from warmup)
  mode = 'topk'

Step 1000 (First Threshold):
  Set mode = 'threshold'
  Micro-batch 0: routes with [2.5, 3.1, 2.8], accumulates [2.7, 3.2, 2.9]
  Micro-batch 1: routes with [2.5, 3.1, 2.8], accumulates [2.6, 3.0, 2.8]
  ...
  step_complete():
    avg = mean([[2.7, 3.2, 2.9], [2.6, 3.0, 2.8], ...]) = [2.65, 3.1, 2.85]
    cutoff_ema = 0.99 * [2.5, 3.1, 2.8] + 0.01 * [2.65, 3.1, 2.85]
                = [2.5015, 3.1000, 2.8005]
    sync across GPUs

Step 1001:
  All GPUs start with synced [2.5015, 3.1000, 2.8005]
  ...
```

---

## Implementation Details

### Part 1: Modify MLP Classes

#### Files to Modify:
- `src/models/gec_shared/shared.py` (GECSharedMLP - parent class)
- `src/models/gec_shared/shared_capacity_threshold.py` (GECSharedMLPCapacityThreshold)

Changes apply to **parent class only**, children inherit automatically.

#### 1.1 Add Accumulator State to __init__

**Location**: `GECSharedMLP.__init__()` in `shared.py`

**Add after cutoff_ema initialization** (around line 40):

```python
# Existing code:
self.cutoff_ema = torch.full((n_routed_experts,), -10.0, dtype=torch.float32)
self.cutoff_ema_count = 0
self.ema_decay = 0.99

# NEW: Add accumulator for gradient accumulation
self.cutoff_accumulator = None  # Will be list of tensors during accumulation
```

**Note**: We use `None` initially and create list on first accumulation. This is simpler than pre-allocating.

**Alternative considered**: Pre-allocate fixed-size tensor
```python
# Alternative (NOT chosen):
max_grad_accum_steps = getattr(config, 'grad_accum_steps', 64)
self.cutoff_accumulator = torch.zeros(n_routed_experts, max_grad_accum_steps)
self.accumulation_count = 0
```

**Why rejected**:
- Requires passing grad_accum_steps to model config (wrong coupling)
- Wastes memory if grad_accum_steps is small
- List is simpler and more flexible

#### 1.2 Modify forward_threshold() to Accumulate

**Location**: `GECSharedMLP.forward_threshold()` in `shared.py`, around lines 82-97

**Current code**:
```python
if self.training:
    with torch.no_grad():
        topk_values, _ = torch.topk(router_logits_flat.t(), k=min(k_target, n_tokens), dim=1)
        cutoffs = topk_values[:, -1]

        # Update EMA
        self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
        self.cutoff_ema_count += 1
```

**New code**:
```python
if self.training:
    with torch.no_grad():
        topk_values, _ = torch.topk(router_logits_flat.t(), k=min(k_target, n_tokens), dim=1)
        cutoffs = topk_values[:, -1]

        # Accumulate cutoffs for averaging at step boundary
        # (EMA will be updated in step_complete())
        if self.cutoff_accumulator is None:
            self.cutoff_accumulator = []
        self.cutoff_accumulator.append(cutoffs)
```

**Key changes**:
- ❌ Remove immediate EMA update
- ✅ Append cutoffs to accumulator list
- ✅ Initialize accumulator on first use

**Why list instead of torch.cat()**:
- Simpler code
- torch.stack() at the end is one operation (vs multiple cats)
- Doesn't matter if size grows (finalized at step boundary)

#### 1.3 Add finalize_cutoff_accumulation() Method

**Location**: New method in `GECSharedMLP` class in `shared.py`

**Add as new method** (suggested location: after forward_threshold(), around line 280):

```python
def finalize_cutoff_accumulation(self):
    """
    Finalize cutoff accumulation at training step boundary.

    Computes arithmetic mean of accumulated topk cutoffs from all micro-batches
    in the current step, then updates the cutoff EMA with this mean.

    This should be called once per training step, after all gradient accumulation
    micro-batches complete.

    Note: This is a no-op if no cutoffs were accumulated (e.g., during eval or topk mode).
    """
    if self.cutoff_accumulator is not None and len(self.cutoff_accumulator) > 0:
        # Stack all accumulated cutoffs: [n_micro_batches, n_routed_experts]
        stacked_cutoffs = torch.stack(self.cutoff_accumulator, dim=0)

        # Compute arithmetic mean across micro-batches: [n_routed_experts]
        avg_cutoffs = stacked_cutoffs.mean(dim=0)

        # Update EMA with averaged cutoffs
        self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * avg_cutoffs
        self.cutoff_ema_count += 1

        # Clear accumulator for next step
        self.cutoff_accumulator = None
```

**Design notes**:
- Returns void (updates state in place)
- Safe to call multiple times (second call is no-op if accumulator is None)
- Handles empty accumulator gracefully
- Clear accumulator after update (critical!)

**Why arithmetic mean not weighted average**:
All micro-batches have equal weight in the final gradient, so equal weight in cutoff averaging makes sense.

### Part 2: Add step_complete() to BaseGPT

#### File to Modify:
- `src/models/model_base.py`

#### 2.1 Add step_complete() Method

**Location**: Add as new method in `BaseGPT` class (suggested location: after `sync_cutoff_ema()`, around line 590)

```python
def step_complete(self):
    """
    Complete training step operations.

    This method should be called at the end of each training step (after optimizer.step())
    to finalize step-level state updates:
    1. Finalize cutoff accumulation (compute mean, update EMA)
    2. Sync cutoff EMA across GPUs (if DDP)

    Future step-boundary operations can be added here (e.g., router temperature updates,
    expert statistics logging, etc.)

    Note: This should only be called during threshold routing mode. During topk warmup,
    EMA updates happen inside forward() and no step-boundary operations are needed.
    """
    import torch.distributed as dist

    # Step 1: Finalize accumulation in each layer
    for block in self.blocks:
        if hasattr(block.mlp, 'finalize_cutoff_accumulation'):
            block.mlp.finalize_cutoff_accumulation()

    # Step 2: Sync across GPUs if using DDP
    if dist.is_initialized():
        for block in self.blocks:
            if hasattr(block.mlp, 'cutoff_ema'):
                # Average cutoff_ema across all GPUs
                dist.all_reduce(block.mlp.cutoff_ema, op=dist.ReduceOp.AVG)

                # Also sync the count (optional, but keeps state consistent)
                if hasattr(block.mlp, 'cutoff_ema_count'):
                    # Count is an int, need to convert to tensor for all_reduce
                    count_tensor = torch.tensor(
                        block.mlp.cutoff_ema_count,
                        dtype=torch.float32,
                        device=block.mlp.cutoff_ema.device
                    )
                    dist.all_reduce(count_tensor, op=dist.ReduceOp.AVG)
                    block.mlp.cutoff_ema_count = int(count_tensor.item())
```

**Design notes**:
- Two clear steps: finalize, then sync
- Works on both single GPU (sync is no-op) and multi-GPU
- Syncs count for consistency (though not strictly necessary)
- Well-documented for future maintainers

**Alternative**: Separate sync from finalize
```python
# Could separate into two methods:
def finalize_step(self): ...
def sync_state(self): ...
```
But this creates ordering dependency and more call sites in train.py.

#### 2.2 Modify or Keep sync_cutoff_ema()?

**Current method** at line 571-589:
```python
def sync_cutoff_ema(self):
    """Synchronize cutoff_ema across all GPUs in DDP training."""
    import torch.distributed as dist
    if not dist.is_initialized():
        return

    for block in self.blocks:
        mlp = block.mlp
        if hasattr(mlp, 'cutoff_ema'):
            dist.all_reduce(mlp.cutoff_ema, op=dist.ReduceOp.AVG)

            if hasattr(mlp, 'cutoff_ema_count'):
                # ... sync count ...
```

**Options**:

**Option A: Keep it unchanged**
- Useful for edge cases (explicit sync without finalization)
- Doesn't interfere with new design
- Recommendation: **Keep it**

**Option B: Add deprecation notice**
```python
def sync_cutoff_ema(self):
    """
    [DEPRECATED] Use step_complete() instead.

    Synchronize cutoff_ema across all GPUs. This method only syncs without
    finalizing accumulation. For normal training, use step_complete() which
    handles both finalization and syncing.
    """
    # ... existing code ...
```

**Option C: Remove it entirely**
- All use cases covered by step_complete()
- Simpler API
- But breaks backward compatibility

**Recommendation**: Keep it (Option A) for now. It's harmless and might be useful for debugging or edge cases.

### Part 3: Update train.py

#### File to Modify:
- `train.py`

#### 3.1 Replace sync_cutoff_ema() Call with step_complete()

**Current code** (lines 251-253):
```python
if ddp and config.training.threshold_warmup_steps >= 0 and \
   step >= config.training.threshold_warmup_steps:
    orig_model.sync_cutoff_ema()
```

**New code**:
```python
# Complete training step: finalize cutoff accumulation and sync
if config.training.threshold_warmup_steps >= 0 and \
   step >= config.training.threshold_warmup_steps:
    orig_model.step_complete()
```

**Changes**:
- ❌ Remove `ddp` condition (step_complete() handles both single/multi GPU)
- ✅ Change method name to `step_complete()`
- ✅ Update comment to reflect new behavior

**Why remove ddp condition?**
- Single GPU still needs finalization (even without sync)
- step_complete() is smart enough to no-op sync if not DDP
- Simpler condition

#### 3.2 Remove Redundant Sync at Mode Switch

**Current code** (lines 210-212):
```python
orig_model.set_routing_mode('threshold')
if ddp:
    orig_model.sync_cutoff_ema()  # ← Remove this
print0(f"→ Switched to threshold routing at step {step}")
```

**New code**:
```python
orig_model.set_routing_mode('threshold')
# No explicit sync needed - step_complete() at end of step 1000 will handle it
print0(f"→ Switched to threshold routing at step {step}")
```

**Why remove?**
- At step 1000, `step_complete()` will be called at end of step (line 251)
- This already syncs cutoffs from warmup
- Redundant sync is wasteful

**Timing analysis**:
```
Step 1000:
  1. Switch to threshold mode (line 210)
  2. Forward pass (uses cutoffs from warmup, may be unsynced)
  3. Backward, optimizer.step()
  4. step_complete() (line 251) - syncs here
```

**Q: Isn't forward pass at step 1000 using unsynced cutoffs?**
**A: Yes, but only for one step.** By step 1001, everything is synced. This is acceptable.

**Alternative**: Keep the sync at line 212 if we want step 1000 to also use synced cutoffs:
```python
orig_model.set_routing_mode('threshold')
if ddp:
    orig_model.sync_cutoff_ema()  # Sync warmup cutoffs before first threshold step
```

**User decision needed**: Accept one step of unsynced cutoffs, or keep the sync?

**Recommendation**: Accept one step of unsynced cutoffs. The difference is minimal and removing redundant sync is cleaner.

### Part 4: Handle GECSharedMLPCapacityThreshold

#### File to Consider:
- `src/models/gec_shared/shared_capacity_threshold.py`

**Key observation**: This class inherits from `GECSharedMLP` and overrides `forward_threshold()`.

#### 4.1 Check if Override Needs Update

**Current override** (line 57+):
```python
def forward_threshold(self, x: torch.Tensor):
    # ... custom threshold routing with capacity constraints ...

    # At line 82-97, same dual-path code:
    if self.training:
        with torch.no_grad():
            topk_values, _ = torch.topk(router_logits_flat.t(), k=min(k_target, n_tokens), dim=1)
            cutoffs = topk_values[:, -1]

            # Update EMA (SAME BUG as parent!)
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
            self.cutoff_ema_count += 1
```

**Update needed**: Replace EMA update with accumulation (same as parent class):

```python
if self.training:
    with torch.no_grad():
        topk_values, _ = torch.topk(router_logits_flat.t(), k=min(k_target, n_tokens), dim=1)
        cutoffs = topk_values[:, -1]

        # Accumulate cutoffs for averaging at step boundary
        if self.cutoff_accumulator is None:
            self.cutoff_accumulator = []
        self.cutoff_accumulator.append(cutoffs)
```

**No other changes needed** because:
- Accumulator is initialized in parent `__init__`
- `finalize_cutoff_accumulation()` is inherited from parent
- Works automatically!

---

## Migration Guide

### For Users

**Before (current code)**:
```python
# During warmup: nothing special
# At step 1000: switch mode, sync
# After step 1000: sync each step

if step == threshold_warmup_steps:
    model.set_routing_mode('threshold')
    if ddp:
        model.sync_cutoff_ema()

# ... training loop ...

if ddp and step >= threshold_warmup_steps:
    model.sync_cutoff_ema()
```

**After (new code)**:
```python
# During warmup: nothing special
# At step 1000: switch mode (sync happens automatically at end of step)
# After step 1000: step_complete() each step

if step == threshold_warmup_steps:
    model.set_routing_mode('threshold')

# ... training loop ...

if step >= threshold_warmup_steps:
    model.step_complete()  # Replaces sync_cutoff_ema()
```

**Key changes**:
- Replace `sync_cutoff_ema()` with `step_complete()`
- Remove `ddp` condition (works for both single/multi GPU)
- Remove explicit sync at mode switch (redundant)

### For Developers

**If you're adding new step-boundary operations**:
1. Add logic to `step_complete()` in `BaseGPT`
2. Keep finalization separate from syncing (finalize first, then sync)
3. Make operations idempotent (safe to call multiple times)

**If you're creating new MLP variants**:
1. Inherit from `GECSharedMLP` to get accumulation automatically
2. If overriding `forward_threshold()`, accumulate instead of updating EMA directly
3. Don't override `finalize_cutoff_accumulation()` unless you need custom logic

---

## Testing Strategy

### Unit Tests

#### Test 1: Accumulation Logic
**File**: `test/test_cutoff_accumulation.py` (new file)

```python
def test_accumulator_initialization():
    """Test that accumulator is None initially."""
    mlp = create_test_mlp()
    assert mlp.cutoff_accumulator is None

def test_accumulation_during_training():
    """Test that forward_threshold accumulates cutoffs."""
    mlp = create_test_mlp()
    mlp.train()

    x = torch.randn(32, 256)  # Batch of tokens
    mlp(x)

    assert mlp.cutoff_accumulator is not None
    assert len(mlp.cutoff_accumulator) == 1  # One forward = one accumulation

def test_multiple_accumulations():
    """Test accumulating across multiple forwards."""
    mlp = create_test_mlp()
    mlp.train()

    for _ in range(4):  # Simulate 4 micro-batches
        x = torch.randn(32, 256)
        mlp(x)

    assert len(mlp.cutoff_accumulator) == 4

def test_finalize_computes_mean():
    """Test that finalization computes arithmetic mean."""
    mlp = create_test_mlp()
    mlp.train()

    # Manually set accumulator with known values
    mlp.cutoff_accumulator = [
        torch.tensor([1.0, 2.0, 3.0]),
        torch.tensor([2.0, 3.0, 4.0]),
    ]
    old_ema = mlp.cutoff_ema.clone()

    mlp.finalize_cutoff_accumulation()

    # Expected mean: [1.5, 2.5, 3.5]
    expected_avg = torch.tensor([1.5, 2.5, 3.5])
    expected_ema = 0.99 * old_ema + 0.01 * expected_avg

    assert torch.allclose(mlp.cutoff_ema, expected_ema)
    assert mlp.cutoff_accumulator is None  # Cleared after finalize

def test_finalize_idempotent():
    """Test that calling finalize multiple times is safe."""
    mlp = create_test_mlp()
    mlp.cutoff_accumulator = [torch.tensor([1.0, 2.0])]

    mlp.finalize_cutoff_accumulation()
    ema_after_first = mlp.cutoff_ema.clone()

    mlp.finalize_cutoff_accumulation()  # Second call
    ema_after_second = mlp.cutoff_ema.clone()

    assert torch.equal(ema_after_first, ema_after_second)  # No change

def test_no_accumulation_during_eval():
    """Test that eval mode doesn't accumulate."""
    mlp = create_test_mlp()
    mlp.eval()

    x = torch.randn(32, 256)
    mlp(x)

    assert mlp.cutoff_accumulator is None  # No accumulation in eval
```

#### Test 2: step_complete() Integration
**File**: `test/test_step_complete.py` (new file)

```python
def test_step_complete_calls_finalize():
    """Test that step_complete calls finalize on all layers."""
    model = create_test_model()
    model.train()

    # Simulate forward pass on all layers
    x = torch.randn(4, 32, 256)
    model(x)

    # All layers should have accumulator
    for block in model.blocks:
        assert block.mlp.cutoff_accumulator is not None

    model.step_complete()

    # All accumulators should be cleared
    for block in model.blocks:
        assert block.mlp.cutoff_accumulator is None

def test_step_complete_without_accumulation():
    """Test that step_complete is safe when no accumulation happened."""
    model = create_test_model()
    model.step_complete()  # Should not crash
```

### Integration Tests

#### Test 3: End-to-End Training Loop
**File**: `test/test_training_integration.py` (new file)

```python
def test_training_with_grad_accum():
    """Test full training loop with gradient accumulation."""
    model = create_test_model()
    optimizer = torch.optim.AdamW(model.parameters())

    grad_accum_steps = 4

    # Simulate one training step with gradient accumulation
    for micro_step in range(grad_accum_steps):
        x = torch.randn(4, 32, 256)
        y = torch.randint(0, 256, (4, 32))

        output = model(x, y)
        loss = output['loss']
        loss.backward()

    optimizer.step()
    optimizer.zero_grad()

    # Complete the step
    model.step_complete()

    # Check that EMA was updated and accumulator cleared
    for block in model.blocks:
        assert block.mlp.cutoff_accumulator is None
        assert block.mlp.cutoff_ema_count > 0

def test_single_forward_without_step_complete():
    """Test that not calling step_complete doesn't crash."""
    model = create_test_model()
    model.train()

    x = torch.randn(4, 32, 256)
    y = torch.randint(0, 256, (4, 32))

    output = model(x, y)  # Forward only
    # Not calling step_complete
    # Should not crash, just accumulates

    assert model.blocks[0].mlp.cutoff_accumulator is not None
```

### Manual Testing

#### Test 4: DDP Training
**Script**: `test/manual_test_ddp.py`

```python
"""
Manual test for DDP training with cutoff accumulation.

Usage:
  torchrun --nproc_per_node=2 test/manual_test_ddp.py
"""

import torch
import torch.distributed as dist
from src.models import BaseGPT

def test_ddp_sync():
    dist.init_process_group("nccl")
    rank = dist.get_rank()

    model = BaseGPT(config).to(rank)
    model = torch.nn.parallel.DistributedDataParallel(model)

    # Each GPU sees different data
    x = torch.randn(4, 32, 256, device=rank) + rank  # Different per GPU!

    # Simulate gradient accumulation
    for _ in range(4):
        output = model(x, None)
        loss = output['loss']
        loss.backward()

    # Print cutoffs before sync
    if rank == 0:
        print(f"GPU-0 cutoff before sync: {model.module.blocks[0].mlp.cutoff_ema}")
    if rank == 1:
        print(f"GPU-1 cutoff before sync: {model.module.blocks[0].mlp.cutoff_ema}")

    # Complete step (should sync)
    model.module.step_complete()

    # Print cutoffs after sync
    if rank == 0:
        print(f"GPU-0 cutoff after sync: {model.module.blocks[0].mlp.cutoff_ema}")
    if rank == 1:
        print(f"GPU-1 cutoff after sync: {model.module.blocks[0].mlp.cutoff_ema}")

    # Verify they're equal
    cutoff_0 = model.module.blocks[0].mlp.cutoff_ema

    # Gather from all ranks
    gathered = [torch.zeros_like(cutoff_0) for _ in range(2)]
    dist.all_gather(gathered, cutoff_0)

    if rank == 0:
        assert torch.allclose(gathered[0], gathered[1]), "Cutoffs not synced!"
        print("✓ Cutoffs synced correctly across GPUs")

if __name__ == '__main__':
    test_ddp_sync()
```

**Expected output**:
```
GPU-0 cutoff before sync: tensor([2.5012, 3.1005, 2.8020])
GPU-1 cutoff before sync: tensor([1.8485, 2.2980, 2.0485])
GPU-0 cutoff after sync: tensor([2.1749, 2.6993, 2.4253])
GPU-1 cutoff after sync: tensor([2.1749, 2.6993, 2.4253])
✓ Cutoffs synced correctly across GPUs
```

#### Test 5: Cutoff Stability Across Steps
**Script**: `test/manual_test_stability.py`

```python
"""Test that cutoffs remain stable across multiple training steps."""

def test_cutoff_stability():
    model = create_test_model()
    model.train()

    cutoff_history = []

    for step in range(100):
        # Gradient accumulation
        for _ in range(4):
            x = torch.randn(4, 32, 256)
            y = torch.randint(0, 256, (4, 32))
            output = model(x, y)
            loss = output['loss']
            loss.backward()

        # Complete step
        model.step_complete()

        # Record cutoff
        cutoff_history.append(model.blocks[0].mlp.cutoff_ema[0].item())

    # Plot or analyze
    import matplotlib.pyplot as plt
    plt.plot(cutoff_history)
    plt.xlabel('Step')
    plt.ylabel('Cutoff (Expert 0)')
    plt.title('Cutoff Stability Over Training')
    plt.savefig('/tmp/cutoff_stability.png')

    # Check for reasonable convergence
    assert cutoff_history[-1] != cutoff_history[0], "Cutoff should evolve"
    assert abs(cutoff_history[-1] - cutoff_history[-10]) < 0.1, "Should stabilize"
```

---

## Edge Cases

### Edge Case 1: grad_accum_steps = 1

**Scenario**: No gradient accumulation.

**Behavior**:
- Accumulator has one element after forward
- `finalize_cutoff_accumulation()` computes mean of one element (= itself)
- EMA updated with this single cutoff

**Expected**: Works correctly, equivalent to immediate update.

**Test**:
```python
def test_no_grad_accum():
    mlp = create_test_mlp()
    mlp.train()

    x = torch.randn(32, 256)
    mlp(x)

    old_ema = mlp.cutoff_ema.clone()
    mlp.finalize_cutoff_accumulation()

    # With one accumulation, mean = the single value
    # EMA should be updated
    assert not torch.equal(mlp.cutoff_ema, old_ema)
```

### Edge Case 2: Calling forward() Multiple Times Without step_complete()

**Scenario**: User calls forward multiple times in a row without finalizing.

**Behavior**:
- Accumulator keeps growing
- Next `step_complete()` will average ALL accumulated cutoffs

**Expected**: Probably not desired, but won't crash. User should call step_complete() regularly.

**Mitigation**: Add warning if accumulator grows too large?
```python
def forward_threshold(self, x):
    # ... accumulation code ...

    if len(self.cutoff_accumulator) > 100:  # Arbitrary threshold
        import warnings
        warnings.warn(
            f"Cutoff accumulator has {len(self.cutoff_accumulator)} entries. "
            "Did you forget to call step_complete()?"
        )
```

### Edge Case 3: Switching Between train() and eval()

**Scenario**:
```python
model.train()
model(x)  # Accumulates
model.eval()
model(x)  # Doesn't accumulate (eval mode)
model.train()
model(x)  # Accumulates again
model.step_complete()  # Finalizes
```

**Behavior**: Accumulator has entries from both train() calls, none from eval().

**Expected**: Works correctly. Eval doesn't interfere with accumulation.

### Edge Case 4: Calling step_complete() During Warmup

**Scenario**: User accidentally calls step_complete() during topk warmup.

**Behavior**:
- `forward_topk()` updates EMA immediately (no accumulation)
- `cutoff_accumulator` is None
- `finalize_cutoff_accumulation()` is no-op

**Expected**: Harmless, just wasted function call.

### Edge Case 5: Mid-Step Checkpoint/Crash

**Scenario**: Training crashes after micro-batch 2 of 4.

**Behavior**:
- Accumulator has 2 entries
- On restart (from checkpoint), accumulator is not saved → starts fresh
- No corruption of EMA

**Expected**: Safe. Accumulator is transient state, not saved in checkpoint.

**Consider**: Should we save accumulator in checkpoint for exact reproducibility?

**Decision**: No. Accumulator is step-internal state, shouldn't persist across restarts.

### Edge Case 6: Changing grad_accum_steps Mid-Training

**Scenario**: User changes from grad_accum_steps=4 to grad_accum_steps=8.

**Behavior**:
- Pre-allocated accumulator (if we had used fixed size) would be too small
- With list-based accumulator: no issue, list grows dynamically

**Expected**: Works fine with current list-based design.

**If we switch to pre-allocated**: Would need dynamic reallocation or error handling.

---

## Performance Considerations

### Memory Overhead

**Per layer**:
- Accumulator: `grad_accum_steps × n_routed_experts` floats
- Example: 4 micro-batches × 8 experts = 32 floats = 128 bytes

**Total for 12-layer model**:
- 12 layers × 128 bytes = 1.5 KB

**Verdict**: Negligible.

### Compute Overhead

**New operations per step**:
1. `torch.stack()`: Concatenates list of tensors (one-time cost)
2. `.mean(dim=0)`: Reduction over micro-batches
3. EMA update: Same as before, just once instead of per micro-batch

**Estimate**:
- Stack + mean: ~0.01ms per layer (12 layers = 0.12ms)
- Forward pass: ~100ms per micro-batch (4 micro-batches = 400ms)

**Overhead**: 0.12ms / 400ms = **0.03%**

**Verdict**: Negligible.

### Communication Overhead (DDP)

**Current (buggy)**: No sync during warmup, sync EMA after each threshold step
- Synced data: `n_layers × n_routed_experts` floats = 12 × 8 = 96 floats

**New**: Same amount of data synced, same frequency

**Change**: None.

### torch.compile Compatibility

**Concerns**:
1. List accumulation (dynamic size) might trigger recompilation?
2. `torch.stack()` on variable-length list?

**Analysis**:
- Accumulation happens inside `if self.training` block with `torch.no_grad()`
- This is typically not compiled (guard condition)
- Stack happens in `finalize_cutoff_accumulation()` which is called outside compiled region

**Verdict**: Should be compatible, but needs testing.

**Alternative if issues arise**: Pre-allocate fixed-size tensor, use indexing instead of list.

---

## Future Extensions

### Extension 1: Configurable Averaging Strategy

**Current**: Always uses arithmetic mean.

**Future**: Support weighted averaging or other strategies.

```python
def finalize_cutoff_accumulation(self, strategy='mean'):
    if strategy == 'mean':
        avg_cutoffs = torch.stack(self.cutoff_accumulator).mean(dim=0)
    elif strategy == 'median':
        avg_cutoffs = torch.stack(self.cutoff_accumulator).median(dim=0).values
    elif strategy == 'ema':
        # EMA across micro-batches (different from EMA across steps)
        ...
```

### Extension 2: Per-Layer step_complete()

If different layers need different step-boundary logic:

```python
# In BaseGPT.step_complete()
for i, block in enumerate(self.blocks):
    if hasattr(block.mlp, 'step_complete'):
        block.mlp.step_complete(layer_id=i)
```

### Extension 3: Other Step-Boundary Operations

**Examples**:
- Update router temperature (annealing)
- Log expert utilization statistics
- Adjust capacity factors dynamically

**Add to step_complete()**:
```python
def step_complete(self):
    # Finalize cutoffs
    self._finalize_cutoffs()

    # Update router temperature
    self._update_router_temperature()

    # Log statistics
    self._log_expert_statistics()

    # Sync all state
    self._sync_training_state()
```

### Extension 4: Distributed Accumulation

For very large grad_accum_steps, might want to accumulate across GPUs:

```python
# Accumulate locally
for micro_step in range(local_grad_accum_steps):
    model(x, y)

# Periodically sync intermediate accumulators
if micro_step % sync_interval == 0:
    model.sync_accumulator()  # New method

# Final step complete
model.step_complete()
```

---

## Checklist

### Implementation
- [ ] Modify `GECSharedMLP.__init__()` to add accumulator
- [ ] Modify `GECSharedMLP.forward_threshold()` to accumulate
- [ ] Add `GECSharedMLP.finalize_cutoff_accumulation()` method
- [ ] Modify `GECSharedMLPCapacityThreshold.forward_threshold()` (same changes)
- [ ] Add `BaseGPT.step_complete()` method
- [ ] Update train.py line 251-253 (replace sync with step_complete)
- [ ] Update train.py line 212 (remove redundant sync)

### Testing
- [ ] Write unit tests for accumulation logic
- [ ] Write unit tests for finalization
- [ ] Write integration test for training loop
- [ ] Manual test with DDP (2 GPUs)
- [ ] Manual test with various grad_accum_steps (1, 4, 8)
- [ ] Check torch.compile compatibility
- [ ] Verify warmup behavior unchanged
- [ ] Check memory usage

### Documentation
- [ ] Update src/models/README.md with new behavior
- [ ] Add docstrings to all new methods
- [ ] Update CLAUDE.md if step_complete becomes a core pattern
- [ ] Add comments in train.py explaining the change

### Validation
- [ ] Run benchmark comparing old vs new behavior
- [ ] Verify training curves match (with seed fixing)
- [ ] Check final model quality unchanged
- [ ] Profile for performance regressions

---

## Summary

**Core changes**:
1. Accumulate cutoffs in list during forward_threshold()
2. Add finalize_cutoff_accumulation() to compute mean and update EMA
3. Add step_complete() to BaseGPT as step-boundary abstraction
4. Replace sync_cutoff_ema() call with step_complete() in train.py

**Benefits**:
- ✅ Cutoffs frozen during micro-batches (fixes inconsistency)
- ✅ Arithmetic averaging across micro-batches (correct semantics)
- ✅ DDP synchronization (fixes divergence)
- ✅ Clean abstraction (step-boundary pattern)
- ✅ Works for single and multi-GPU
- ✅ Minimal performance overhead

**Risks**:
- torch.compile compatibility (needs testing)
- Edge cases with dynamic accumulator size (mitigated by list-based design)
- Potential confusion about when to call step_complete() (mitigated by clear docs)

**Recommendation**: Proceed with implementation, test thoroughly, and monitor for edge cases.
