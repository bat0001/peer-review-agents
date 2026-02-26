# EP Training Deadlock Bug

## Status: OPEN

## Symptoms
- Training hangs/deadlocks when running with `model.expert_parallel=true`
- Happens before any training steps complete
- Likely during initialization or first forward pass

## Investigation

### What's Implemented
1. **Initialization (DONE, TESTED, WORKS)**
   - `compute_init(expert_parallel=True)` uses `seed + rank` for divergent init
   - `broadcast_dp_params()` syncs DP params, keeps EP experts unique
   - Test passes: `torchrun --nproc_per_node=2 test/test_ep_init.py`

2. **Model Selection (DONE)**
   - `GECSharedMLP` and `GECMLP` use `ParallelExperts` when `config.expert_parallel=True`
   - Import fixed in `src/ops/all_to_all.py` (`dist.Handle` → `dist.Work`)

3. **Optimizer (DONE)**
   - 3rd optimizer (local Muon) for EP expert weights
   - `train.py` handles 3 optimizers

4. **Checkpointing (DONE)**
   - EP-aware save gathers expert shards to rank 0

### Suspected Cause
Deadlock likely occurs in one of:

1. **`broadcast_dp_params()` in `init_model_weights()`**
   - This broadcasts all non-expert params from rank 0
   - Could hang if ranks disagree on which params to broadcast

2. **`ParallelExperts.forward_topk()` all-to-all communication**
   - `dist.all_gather_into_tensor()` for router logits
   - `all_to_all()` for token dispatch
   - `all_to_all()` for expert output return
   - Split sizes computed with `.item()` calls which sync GPU→CPU

3. **Mismatch between `ParallelExperts` return interface and `GECSharedMLP` expectations**
   - `ParallelExperts` returns global `topk_indices`
   - `GECSharedMLP` expects local indices for scatter
   - The scatter operation may not work correctly with EP

### Debug Prints Added
Debug prints added to `parallel_experts_manual.py` at:
- Step 1: Router logits computation
- Step 2: All-gather router logits
- Step 3: Top-k selection
- Step 4: Dispatch index computation
- Step 5: All-to-all forward

### Files Modified
- `src/models/gec_shared.py` - Uses ParallelExperts when EP
- `src/models/gec.py` - Uses ParallelExperts when EP
- `src/optimizers/factory.py` - 3rd optimizer for EP
- `train.py` - 3 optimizer handling, EP checkpoint save
- `src/ops/all_to_all.py` - Fixed type annotation
- `src/models/engines/parallel_experts_manual.py` - Debug prints

### Next Steps
1. Run with debug prints to identify exact hang location
2. Check if `broadcast_dp_params` is the culprit (test init separately)
3. Verify all-to-all split sizes are symmetric across ranks
4. Consider if `ParallelExperts` needs different return interface

### Commands to Reproduce
```bash
# This hangs:
CUDA_VISIBLE_DEVICES=0,4 torchrun --nproc_per_node=2 train.py \
    model_size=tiny mlp=gec_shared +experiment=debug \
    model.expert_parallel=true training.max_steps=5

# This works:
CUDA_VISIBLE_DEVICES=0,4 torchrun --nproc_per_node=2 test/test_ep_init.py
```

## Related Files
- `src/models/engines/parallel_experts_manual.py` - EP engine
- `src/utils/distributed.py` - `broadcast_dp_params()`
- `memory/archive/completed/expert_parallel_train_integration.md` - Original plan
