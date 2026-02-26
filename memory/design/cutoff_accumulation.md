# Cutoff Accumulation Design

**Date**: 2025-11-04
**Status**: Implemented
**Related**: Bug 2 - DDP cutoff divergence + micro-batch inconsistency

## Overview

During threshold routing with gradient accumulation, cutoffs must remain frozen across micro-batches to preserve gradient accumulation semantics. Additionally, in DDP training, cutoff EMAs must be synchronized across GPUs.

**Solution**: A "step-boundary pattern" where cutoffs are frozen during micro-batches, accumulated statistics are averaged, and EMA is updated once per training step via `step_complete()`.

**2026-02 update (two-gate schedule)**:
- `training.ema_start_steps`: controls when EMA updates start
- `training.threshold_warmup_steps`: controls when training switches from topk to threshold
- For non-threshold-capable models, both fields are ignored

## Design Philosophy

### Core Principles

1. **Step-boundary pattern**: Training steps are the fundamental unit. State updates happen at step boundaries, not during forward passes.

2. **Separation of concerns**:
   - Forward pass: Computes outputs, accumulates statistics
   - Step boundary: Finalizes accumulated statistics, updates training state
   - BaseGPT: Coordinates across layers
   - MLP classes: Implement domain logic

3. **Explicit over implicit**: Rather than hiding finalization in existing methods, make it explicit with `step_complete()`.

4. **Works for all cases**: Single GPU, multi-GPU, any gradient accumulation steps.

### Alternatives Considered

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

## Architecture

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

### Behavior By Gate

#### EMA Gate (`ema_start_steps`)

- `forward_topk()` / `forward_threshold()` accumulate cutoff statistics (sum/count).
- Before `ema_start_steps`, `step_complete()` clears accumulators without updating EMA.
- At and after `ema_start_steps`, `step_complete()` applies one EMA update per training step.

#### Routing Gate (`threshold_warmup_steps`)

- Before `threshold_warmup_steps`, training routing is topk.
- At and after `threshold_warmup_steps`, training routing is threshold.
- DDP cutoff synchronization runs only after the routing switch gate.

### State Transitions Example

```
Step 199 (before EMA start):
  cutoff_ema = [0.0, 0.0, 0.0]
  mode = 'topk'
  step_complete(): clear accumulators, no EMA update

Step 200 (EMA starts, still topk routing):
  mode = 'topk'
  step_complete():
    avg = sum / count
    cutoff_ema = 0.99 * cutoff_ema + 0.01 * avg

Step 999 (last topk step before switch):
  mode = 'topk'

Step 1000 (First Threshold):
  Set mode = 'threshold'
  Micro-batch 0: routes with threshold(cutoff_ema), accumulates sum=[...], count=1
  Micro-batch 1: routes with threshold(cutoff_ema), accumulates sum=[...], count=2
  ...
  step_complete():
    avg = sum / count
    cutoff_ema = 0.99 * cutoff_ema + 0.01 * avg
    sync across GPUs
```

## Implementation Overview

### MLP Classes

**Added state**:
- `cutoff_accum_sum`: Tensor accumulating sum of cutoffs (persistent=False)
- `cutoff_accum_count`: Tensor accumulating count of steps (persistent=False)
- (Replaced previous list-based accumulator which caused graph breaks)

**Modified behavior**:
- `forward_threshold()`: Adds cutoffs to accumulation tensors instead of updating EMA immediately
- New `finalize_cutoff_accumulation()`: Computes mean from sum/count, updates EMA, resets tensors

**Why arithmetic mean**: All micro-batches have equal weight in the final gradient, so equal weight in cutoff averaging makes sense.

### BaseGPT Coordination

**New method**: `step_complete()`
1. Calls `finalize_cutoff_accumulation()` on all layers
2. Synchronizes cutoff EMAs across GPUs (if DDP)

**Abstraction benefit**: Single call site in training loop, easy to extend with future step-boundary operations (e.g., router temperature updates, expert statistics logging).

### Training Loop Integration

**Current pattern**:
```python
orig_model.step_complete(
    step=step,
    ema_start_steps=config.training.ema_start_steps,
    threshold_warmup_steps=config.training.threshold_warmup_steps,
    threshold_capable=threshold_capable_model,
)
```

**Changes**:
- EMA update timing is controlled independently from routing switch timing.
- DDP sync remains automatic once threshold routing is active.

## DDP Synchronization

### Timing

Synchronization happens **after** optimizer.step(), as part of `step_complete()`:

```
backward() → gradients computed
optimizer.step() → weights updated
step_complete() → cutoff EMA synchronized
```

### Why This Timing

- EMA reflects training state that produced the gradients
- Synchronization once per step (not per micro-batch) is efficient
- All GPUs start next step with identical cutoffs

### Implementation

Uses one batched `torch.distributed.all_gather_object()` at step boundary:
- Each GPU finalizes local EMA updates first
- All cutoff EMA tensors are gathered for all MoE blocks
- Per-block means are computed and copied back
- All GPUs start next step with identical cutoff values

## Future Extensions

The step-boundary pattern via `step_complete()` provides a natural extension point for other step-level operations:

- Router temperature annealing
- Expert utilization logging
- Dynamic capacity factor adjustment
- Any operation that should happen once per training step

## References

- Implementation: `src/models/engines/engine.py` and `src/models/engines/parallel_experts_manual.py` (accumulation), `src/models/model_base.py` (step_complete)
- Plan: `memory/archive/completed/cutoff_accumulation_implementation.md`
- Related: `memory/design/threshold_routing_design.md` (dual-mode training)
