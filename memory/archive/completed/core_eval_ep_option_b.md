# Plan B: EP-safe CORE eval via shape-aligned distributed batching

## Goal
Preserve distributed CORE eval throughput **without rank-divergent collectives** by guaranteeing identical tensor shapes across ranks for every forward pass.

## Key idea
Each rank evaluates **different examples**, but for every step all ranks use the **same tensor shape** `(num_prompts, max_seq_len)`:
- For each task, bucket examples by `num_prompts` (choices count) and task type.
- At each step, every rank pulls one example from the same bucket.
- Ranks compute their local `max_seq_len`, then all-gather to compute a **global max** and pad locally.
- Forward passes align → NCCL collectives align → no timeouts.

## Files to edit
- `src/eval/core.py`
- (optional) `src/config.py` to add a small config switch for eval mode, e.g. `eval.core_mode: broadcast|shape_aligned|auto`

## Detailed steps

### 1) Add eval mode selection
Add a config field to control strategy (optional but recommended):
```python
# src/config.py (EvalConfig)
core_eval_mode: str = "auto"  # auto | broadcast | shape_aligned
```
Selection logic in `evaluate_model` or `evaluate_task`:
```python
if dist.is_initialized() and dist.get_world_size() > 1 and model.config.expert_parallel:
    mode = config.eval.core_eval_mode
    if mode == "broadcast":
        ...  # Option A path
    elif mode == "shape_aligned" or mode == "auto":
        ...  # Option B path
```

### 2) Bucket examples by prompt count
In `src/eval/core.py`, add a helper that scans each task’s dataset and assigns each example to a bucket:
```python
# task_type: multiple_choice or schema
# num_prompts: len(item["choices"]) or len(item["context_options"]) or 1 for LM
buckets: dict[int, list[int]]  # num_prompts -> list of indices
```
Notes:
- Use deterministic shuffle (existing `shuffle_rng = random.Random(1337)`), then bucket so order is stable.
- Keep `max_per_task` slicing before bucketing to keep runtime bounded.

### 3) Distributed shape-aligned evaluation loop
For each bucket (fixed `num_prompts`):
1. **Shard indices by rank**: each rank gets indices `bucket_indices[rank::world_size]`.
2. **Iterate in lock-step**: use `step = 0..max_len-1` where `max_len = max(len(shard) for shard)`.
3. Each rank:
   - If it has an example at this `step`, build prompts, tokenize, and stack.
   - If not, create a dummy example of shape `(num_prompts, 1)` (or `(num_prompts, pad_len)`), and flag `valid=False`.
4. **Global max length**:
   - Each rank computes `local_max_len = input_ids.size(1)`.
   - Use `dist.all_gather` to get all `local_max_len`, compute `global_max_len`.
5. **Pad to global shape**:
   - Pad `input_ids` to `(num_prompts, global_max_len)` on every rank.
6. **Forward pass**:
   - All ranks call `forward_model(model, input_ids)`.
7. **Local correctness**:
   - If `valid=False`, skip scoring (count=0).
   - Otherwise, compute `is_correct` exactly as today.
8. **Reduce**:
   - `dist.all_reduce(correct_sum)` and `dist.all_reduce(count)` to get global accuracy.

Pseudo-snippet (core of the loop):
```python
for num_prompts, indices in buckets.items():
    shard = indices[rank::world_size]
    max_steps = max_len_across_ranks(len(shard))
    for step in range(max_steps):
        if step < len(shard):
            input_ids, meta = build_example(shard[step])
            valid = True
        else:
            input_ids = make_dummy(num_prompts)
            meta = None
            valid = False

        local_len = torch.tensor([input_ids.size(1)], device=device, dtype=torch.long)
        lens = [torch.zeros_like(local_len) for _ in range(world_size)]
        dist.all_gather(lens, local_len)
        global_len = int(torch.stack(lens).max().item())

        input_ids = pad_to_len(input_ids, global_len)
        losses, preds = forward_model(model, input_ids)

        if valid:
            correct_sum += int(compute_correctness(losses, preds, meta))
            count += 1

# After all buckets: all_reduce correct_sum/count
```

### 4) Implement helper functions
Add helpers in `src/eval/core.py`:
- `_num_prompts(item, task_type)`
- `_build_example(item, task_meta)` (returns `input_ids`, `meta`)
- `_pad_input_ids(input_ids, pad_token_id, target_len)`
- `_reduce_max_len(local_len)` using `all_gather`

These helpers should reuse existing `render_prompts_*` and `batch_sequences_*` to avoid logic drift.

### 5) Preserve existing correctness logic
Use the same scoring rules as today for each task type.
Only change the **scheduling** and **padding** to make shapes consistent across ranks.

### 6) Tests / validation (post-approval)
- 2-GPU EP run, small eval:
  ```bash
  CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 \
    train.py +experiment=debug eval.core_metric_max_per_task=8 eval.core_eval_mode=shape_aligned
  ```
- Compare CORE metric to single-GPU baseline (small subset, should match).
- Verify no NCCL timeouts.

## Risks / trade-offs
- **More code complexity** than Option A (bucketing + step synchronization).
- **More memory** due to padding to global max length per step.
- Potential **slowdown** if some ranks have much longer examples; mitigated by bucketing.

## Summary
Option B keeps CORE eval distributed while guaranteeing shape-aligned forward passes. It’s more complex than Option A but avoids the “all ranks do the same work” overhead.
