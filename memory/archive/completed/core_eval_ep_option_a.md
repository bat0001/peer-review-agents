# Plan A: EP-safe CORE eval via broadcasted inputs (rank0 drives, all ranks forward)

## Goal
Make CORE eval safe for Expert Parallelism (EP) by ensuring **all ranks run identical forward passes with identical tensor shapes**, preventing NCCL collectives from diverging. This is a tactical fix; it prioritizes correctness and avoids large refactors.

## Key idea
- **Rank 0** builds the example’s `input_ids` (tokenized prompts) + metadata.
- **All ranks** receive the same `input_ids` via broadcast and run `model(...)` so EP collectives line up.
- **Only rank 0** computes correctness; the scalar accuracy is broadcast to all ranks for consistent results.

## Files to edit
- `src/eval/core.py`

## Detailed steps

### 1) Add EP detection and a sync path
In `src/eval/core.py`, add a small helper to detect EP mode:
```python
rank = dist.get_rank() if dist.is_initialized() else 0
world_size = dist.get_world_size() if dist.is_initialized() else 1
is_ep = bool(getattr(getattr(model, "config", None), "expert_parallel", False))
use_sync = is_ep and world_size > 1
```

### 2) Add broadcast helpers (shape + tensor)
Add private helpers near the top of `src/eval/core.py`:
```python
def _broadcast_tensor(src_tensor: torch.Tensor | None, device: torch.device, dtype: torch.dtype):
    # Broadcasts shape first, then payload. Returns tensor on all ranks.
    rank = dist.get_rank()
    if rank == 0:
        shape = torch.tensor(src_tensor.shape, device=device, dtype=torch.long)
    else:
        shape = torch.empty(2, device=device, dtype=torch.long)  # (bsz, seq_len)
    dist.broadcast(shape, src=0)
    shape = tuple(int(x) for x in shape.tolist())
    if rank != 0:
        src_tensor = torch.empty(shape, device=device, dtype=dtype)
    dist.broadcast(src_tensor, src=0)
    return src_tensor


def _broadcast_obj(obj):
    payload = [obj]
    dist.broadcast_object_list(payload, src=0)
    return payload[0]
```
Notes:
- Use NCCL broadcasts for tensors, `broadcast_object_list` for metadata (task type, start/end indices, gold label). 
- Keep metadata small to avoid overhead.

### 3) Introduce an EP-safe evaluation helper
Add a new helper function (or branch inside `evaluate_task`) that uses broadcasted inputs:
```python
def _evaluate_task_ep_sync(model, tokenizer, data, device, task_meta):
    rank = dist.get_rank()
    world_size = dist.get_world_size()

    # Only rank 0 needs to keep the full data; others only need the length.
    if rank == 0:
        num_examples = len(data)
    else:
        num_examples = 0
    num_examples = int(_broadcast_obj(num_examples))

    correct = 0

    for idx in range(num_examples):
        if rank == 0:
            # Build prompts + tokenization on rank 0 only
            item = data[idx]
            task_type = task_meta["task_type"]
            # Use existing logic to get tokens/start/end
            if task_type == "multiple_choice":
                prompts = render_prompts_mc(item, task_meta["continuation_delimiter"], fewshot_examples=...)
                tokens, start_idxs, end_idxs = batch_sequences_mc(tokenizer, prompts)
            elif task_type == "schema":
                prompts = render_prompts_schema(...)
                tokens, start_idxs, end_idxs = batch_sequences_schema(...)
            else:
                prompts = render_prompts_lm(...)
                tokens, start_idxs, end_idxs = batch_sequences_lm(...)
            input_ids = stack_sequences(tokens, pad_token_id).to(device)
            meta = {
                "task_type": task_type,
                "start_idxs": start_idxs,
                "end_idxs": end_idxs,
                "gold": item.get("gold", None),
            }
        else:
            input_ids = None
            meta = None

        meta = _broadcast_obj(meta)
        input_ids = _broadcast_tensor(input_ids, device=device, dtype=torch.long)

        # All ranks run forward so EP collectives match
        losses, predictions = forward_model(model, input_ids)

        # Rank 0 computes correctness
        is_correct = 0
        if rank == 0:
            if meta["task_type"] == "language_modeling":
                si, ei = meta["start_idxs"][0], meta["end_idxs"][0]
                pred = predictions[0, si - 1:ei - 1]
                actual = input_ids[0, si:ei]
                is_correct = int(torch.all(pred == actual).item())
            else:
                mean_losses = [losses[i, si - 1:ei - 1].mean().item()
                               for i, (si, ei) in enumerate(zip(meta["start_idxs"], meta["end_idxs"]))]
                pred_idx = mean_losses.index(min(mean_losses))
                is_correct = int(pred_idx == meta["gold"])

        # Broadcast correctness so all ranks have same accuracy
        is_correct = int(_broadcast_obj(is_correct))
        correct += is_correct

    return correct / max(1, num_examples)
```

### 4) Wire `evaluate_task` to use EP sync path
Modify `evaluate_task(...)` to choose the sync path when EP is enabled:
```python
if dist.is_initialized() and dist.get_world_size() > 1 and getattr(model.config, "expert_parallel", False):
    return _evaluate_task_ep_sync(...)
# else: keep existing per-rank sharding path
```

### 5) Ensure evaluate_model keeps deterministic data ordering
- Keep existing shuffle (`shuffle_rng = random.Random(1337)`) and slicing by `max_per_task` on **all ranks** or just on rank 0.
- If only rank 0 reads data, broadcast `num_examples` to all ranks as above.

### 6) Tests / validation (post-approval)
- 2-GPU EP run with small core eval:
  ```bash
  CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 \
    train.py +experiment=debug eval.core_metric_max_per_task=8
  ```
  Expect no NCCL timeouts.
- Compare CORE metric against single-GPU to ensure parity (within minor noise).

## Risks / trade-offs
- **Slow**: all ranks run identical forward passes (no data parallelism in CORE eval). This is OK for a tactical fix.
- **Extra CPU on rank 0**: tokenization and prompt rendering are serialized.

## Summary
Option A is the smallest, safest change: align EP collectives by broadcasting the exact `input_ids` per example. It preserves correctness and avoids NCCL hangs with minimal code movement.
