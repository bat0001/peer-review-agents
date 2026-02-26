# Expert Parallelism Implementation Plan

## Overview

Add Expert Parallelism (EP) to nano_gec_clean. Each GPU owns `E/world_size` experts. Tokens dispatched via all-to-all, computed locally, results combined via reverse all-to-all.

## Architecture

```
Pure EP: All GPUs participate in expert parallelism (no separate DP groups)
- world_size GPUs, each owns local_experts = E / world_size experts
- Router is replicated (DP) across all GPUs
- Each rank owns experts [rank * local_experts, (rank+1) * local_experts)

Parameter types:
- Router: Replicated, DistMuon with world
- Routed experts: Sharded, each rank owns local subset, Original Muon (no dist sync)
```

## Files

### 1. `src/ops/all_to_all.py` ✅ DONE
AllToAllOp with autograd support:
- Wraps `dist.all_to_all_single`
- Backward swaps send/recv counts
- Returns `(output_tensor, handle)` for async support

### 2. `src/models/engines/parallel_experts_manual.py` ✅ DONE
`ParallelExperts` class - standalone EP implementation:
- Each GPU owns `local_experts = n_routed_experts // world_size` experts
- Router replicated on all GPUs
- Expert weights as `nn.ParameterList` (local experts only)
- `forward_topk`: 8-step EP forward pass
- `forward_threshold`: TODO

### 3. No separate topology module needed
Pure EP uses `dist.get_world_size()` and `dist.get_rank()` directly.

## Forward Algorithm (8 Steps)

Implementation in `parallel_experts_manual.py`:

```
Step 1: ROUTER LOCAL
  router_logits = self.router(x).float()  # (B, T, n_routed_experts)
  router_logits_flat = router_logits.view(-1, n_routed_experts)  # (n_tokens, E)

Step 2: ALL-GATHER LOGITS
  global_router_logits = all_gather(router_logits_flat)  # (world_size * n_tokens, E)
  All GPUs now have identical global view of all tokens

Step 3: GLOBAL TOP-K (identical on all GPUs)
  k_global = k * world_size  # global capacity
  topk_values, topk_indices = topk(global_router_logits.t(), k=k_global)  # (E, k_global)

Step 4: COMPUTE DISPATCH INDICES
  # Which tokens does THIS rank send?
  local_mask = (topk_indices >= rank * n_tokens) & (topk_indices < (rank + 1) * n_tokens)
  send_indices = topk_indices[local_mask].flatten()

  # Split sizes for all-to-all
  input_split_sizes = [count of local tokens going to rank r's experts]
  output_split_sizes = [count of tokens this rank receives from rank r]

Step 5: COLLECT TOKENS FOR DISPATCH
  tokens_to_send = x_flat[send_indices % n_tokens].contiguous()

Step 6: ALL-TO-ALL DISPATCH
  tokens_received = all_to_all(tokens_to_send, output_split_sizes, input_split_sizes)
  tokens_received = tokens_received.view(local_experts, k_global, C)

Step 7: EXPERT FORWARD (BMM)
  h = _batched_expert_forward(tokens_received)  # (local_experts, k_global, C)

Step 8: ALL-TO-ALL COMBINE + WEIGHT APPLICATION
  expert_outputs_received = all_to_all(h.view(-1, C), input_split_sizes, output_split_sizes)
  # Weights from LOCAL logits for gradient flow
  weights_flat = apply_router_activation(router_logits_flat[send_indices % n_tokens, expert_ids])
```

**Key insight**: Gradient flow through `router_logits_flat` (local), not `global_router_logits`.

## Communication Pattern

| Mode | Communication |
|------|---------------|
| Top-K Training | 1 all-gather + 2 all-to-all |
| Threshold (TODO) | TBD |

## TODO

- [ ] Implement `forward_threshold` using `cutoff_ema`
- [ ] Integration with train.py
- [ ] Checkpoint collection/distribution for EP

## Integration with train.py

### Optimizer Setup
```python
# Separate params by type
router_params = []      # router weights (replicated)
expert_params = []      # routed expert weights (local only)

for name, p in model.named_parameters():
    if 'expert_weight' in name:
        expert_params.append(p)
    else:
        router_params.append(p)

# Router: DistMuon (synced across all GPUs)
router_optimizer = DistMuon(router_params, ...)

# Expert params: Original Muon (no sync - each GPU has unique experts)
expert_optimizer = Muon(expert_params, ...)
```

### Checkpoint Handling

**Saving** (gather expert weights to rank 0):
```python
def save_checkpoint_ep(output_dir, step, model, optimizers, config):
    # Gather expert weights from all ranks
    expert_state = {}
    for name, param in model.named_parameters():
        if 'expert_weight' in name:
            gathered = [torch.empty_like(param) for _ in range(world_size)]
            dist.all_gather(gathered, param)
            if rank == 0:
                expert_state[name] = torch.cat(gathered, dim=0)  # Stack by expert

    if rank == 0:
        checkpoint = {
            'step': step,
            'model_state_dict': model.state_dict(),  # Local experts only
            'gathered_expert_state': expert_state,   # Full experts
            'optimizer_state_dicts': [opt.state_dict() for opt in optimizers],
        }
        torch.save(checkpoint, path)
```

**Loading** (scatter to appropriate ranks):
```python
def load_checkpoint_ep(path, model):
    checkpoint = torch.load(path)

    if 'gathered_expert_state' in checkpoint:
        # Scatter expert weights to appropriate ranks
        for name, full_param in checkpoint['gathered_expert_state'].items():
            # Split by world_size, take this rank's slice
            local_param = full_param.chunk(world_size)[rank]
            model.get_parameter(name).data.copy_(local_param)
    else:
        # Standard load (non-EP checkpoint)
        model.load_state_dict(checkpoint['model_state_dict'])
```

## Why GEC EP is Simpler than MegaBlocks

**GEC uses expert-selects-token routing:**
- Each expert selects exactly k tokens via top-k
- Result: `indices_batched (E, k)` - already organized by expert
- No need to sort tokens by expert ID

**No hidden sharding:**
- Each GPU owns complete experts, no partial weights

**Fixed k per expert:**
- All experts have exactly k tokens (in top-k mode)
- No variable bin sizes, no dynamic padding
