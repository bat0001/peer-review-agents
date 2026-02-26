# EP Training Deadlock Bug v2

## Status: FIXED ✓

## Summary
Training hangs/deadlocks when running with `model.expert_parallel=true`.

## All Fixes Applied

### Fix 1: Flat API Refactor (Session 1)
The API mismatch between `ParallelExperts` and `ExpertEngine` has been fixed by unifying to a **flat API**:

**New unified API (both engines)**:
```python
# Returns:
h_flat: (total_active, C)      # Variable size, only valid entries
indices_flat: (total_active,)  # 1D flat token indices
weights_flat: (total_active,)  # Matches indices
fanout: (n_tokens,)            # Per-token expert count
```

**Files modified**:
- `src/models/engines/engine.py` - forward_topk, forward_threshold return flat
- `src/models/engines/parallel_experts_manual.py` - already flat, cleaned up debug prints
- `src/models/gec.py` - use indices_flat directly
- `src/models/gec_shared.py` - use indices_flat directly
- `src/ops/scatter_backends.py` - accept flat indices
- `src/kernels/csr.py` - added `build_slot_indices_flat()`
- `src/ops/csr.py` - updated CSRScatterOp for flat API
- `src/ops/csr_optimized.py` - updated for flat API

### Fix 2: Evaluation deadlock (Session 2)

**Root cause**: With EP, `model.forward()` uses all-to-all collective operations.
The original code ran evaluation rank-0 only:
```python
if step % eval_interval == 0:
    if master_process:
        evaluate(model, ...)  # Only rank 0 runs forward!
    dist.barrier()  # Rank 1 waits here
```

This caused deadlock: rank 0 waits for rank 1 in all-to-all, rank 1 waits for rank 0 at barrier.

**Fix**: All ranks must run evaluation with EP:
```python
if step % eval_interval == 0:
    if expert_parallel:
        # EP: All ranks run eval (model forward needs all-to-all)
        evaluate(model, ..., logger if master_process else None, ...)
    elif master_process:
        evaluate(model, ..., logger, ...)
    dist.barrier()
```

**File modified**: `train.py` lines 363-376

### Fix 3: Missing forward_threshold in ParallelExperts (Session 2)

**Root cause**: When `routing_mode=None` (default), eval mode uses threshold routing
(because `self.training=False`). But `ParallelExperts.forward_threshold()` was not implemented.

**Fix**: Simple fallback until proper implementation:
```python
def forward_threshold(self, x, layer_idx=0, is_shared=False):
    """Threshold routing - not yet implemented for EP, falls back to topk."""
    # TODO: Implement proper threshold routing for EP
    return self.forward_topk(x, layer_idx, is_shared)
```

**File modified**: `src/models/engines/parallel_experts_manual.py` line 195-198

## Tests Passed

```bash
# Full EP training with evaluation and checkpointing:
CUDA_VISIBLE_DEVICES=8,9 torchrun --nproc_per_node=2 train.py \
    +experiment=debug model.expert_parallel=true training.max_steps=25

# Results:
# - Loss: 10.8 → 7.1 → 6.8 (decreasing)
# - Eval at step 20: eval_loss=6.88
# - Checkpoint saved: "Saved (EP full model): ...checkpoint_step_25.pt"
# - "Training complete!"
```

## Previous Fixes (for reference)

### Bug 1: Meta device tensor (FIXED in Session 1)
`self.local_expert_ids` was created on meta device during model init.
**Fix**: Recompute on correct device in forward.

### Bug 2: API mismatch (FIXED in Session 1)
Shape mismatch between EP returns and GEC wrapper expectations.
**Fix**: Unified flat API across all engines and backends.
