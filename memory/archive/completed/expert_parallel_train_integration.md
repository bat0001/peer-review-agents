# Expert Parallelism Training Integration Plan

## Overview

Integrate `ParallelExperts` (EP) engine with `train.py`. The key challenge is that EP expert weights are sharded (each rank owns different experts), requiring both a unique initialization strategy ("Seed & Sync") and a separate local optimizer setup.

## 1. Initialization Strategy: "Seed, Sync & Shard"

### Problem
`BaseGPT.init_weights` uses a fixed seed, which would make expert weights identical across ranks. However:
- **DP Parameters** (Attention, Router, Embeddings) MUST be identical (synced).
- **EP Parameters** (Experts) MUST be different (sharded/unique).

### Solution
1. **Divergent Initialization**: 
   - In `compute_init`, if `expert_parallel=True`, use `seed + rank`.
   - Result: All parameters start unique on every rank.
2. **Force Convergence (Sync)**:
   - Immediately after `init_weights`, call `broadcast_dp_params`.
   - This function broadcasts all parameters *except* `expert_weight` from Rank 0 to all other ranks.
   - Result: DP params are synced; EP experts remain unique.

## 2. Optimizer Architecture

**Optimizer Factory** (`src/optimizers/factory.py`):
- `DistAdamW`: embeddings, lm_head, router (replicated via all-gather)
- `DistMuon`: 2D/3D matrices in Attention/DenseMLP (synced across ranks)
- **NEW**: `LocalMuon`: EP expert weights (local to each rank, NO sync)

**Parameter Grouping**:
| Parameter Type | EP Behavior | Optimizer |
|---------------|-------------|-----------|
| Embeddings (`wte`) | Replicated | DistAdamW (no change) |
| LM head | Replicated | DistAdamW (no change) |
| Transformer blocks | Replicated | DistMuon (no change) |
| Router weights | Replicated (DP) | DistAdamW (no change) |
| **Expert weights** | **Sharded** | **Muon** (local instance, NO sync) |

### Why Local Muon for Expert Weights?
Current `DistMuon` performs `reduce_scatter` -> `compute` -> `all_gather`. 
For EP, each rank owns completely disjoint experts. There is no shared gradient to average, and we do not want to replicate the parameters. Therefore, they must use a standard `Muon` instance running locally on each GPU.

## 3. Implementation Plan

### Step 1: Update `src/utils/distributed.py`
```python
def compute_init(seed: int = 42, expert_parallel: bool = False):
    # ... setup ...
    ddp, rank, local_rank, world_size = get_dist_info()
    
    # EP mode: rank-specific seed for different expert weights
    if expert_parallel and ddp:
        effective_seed = seed + rank
    else:
        effective_seed = seed
    
    torch.manual_seed(effective_seed)
    torch.cuda.manual_seed(effective_seed)
    # ... rest of init ...

def broadcast_dp_params(model: nn.Module):
    """Broadcast DP params from rank 0. Skip EP expert weights."""
    if not is_ddp(): return
    
    # Broadcast parameters
    for name, param in model.named_parameters():
        if 'expert_weight' in name: continue
        dist.broadcast(param.data, src=0)
        
    # Broadcast buffers (e.g. cutoff_ema)
    for name, buffer in model.named_buffers():
        dist.broadcast(buffer, src=0)
```

### Step 2: Modify `src/optimizers/factory.py`
```python
def create_hybrid_optimizer(..., expert_parallel: bool = False):
    # ... setup lists ...
    local_expert_params = []
    
    for name, param in model.named_parameters():
        if not param.requires_grad: continue

        if expert_parallel and 'expert_weight' in name:
            local_expert_params.append(param)
        elif 'wte' in name:
            embedding_params.append(param)
        # ... standard classification ...

    # Create standard optimizers
    if use_dist:
        adamw = DistAdamW(adam_groups, **adamw_kwargs)
        muon = DistMuon(matrix_params, lr=matrix_lr, momentum=0.95)
        
        if expert_parallel and local_expert_params:
            # EP: Return 3 optimizers
            expert_opt = Muon(local_expert_params, lr=matrix_lr, momentum=0.95)
            return adamw, muon, expert_opt
            
    return adamw, muon
```

### Step 3: Update `train.py` (Init & Opt)
```python
# 1. Initialization
expert_parallel = config.model.get('expert_parallel', False)
compute_init(..., expert_parallel=expert_parallel)
model.init_weights()
if expert_parallel:
    broadcast_dp_params(model)

# 2. Optimizer Creation
opt_result = create_hybrid_optimizer(..., expert_parallel=expert_parallel)
if len(opt_result) == 3:
    adamw_opt, muon_opt, expert_opt = opt_result
    optimizers = [adamw_opt, muon_opt, expert_opt]
else:
    adamw_opt, muon_opt = opt_result
    optimizers = [adamw_opt, muon_opt]
```

### Step 4: Checkpointing Logic (Detailed)

**Saving (`train.py`)**:
```python
def save_checkpoint_ep(output_dir, step, model, optimizers, config):
    rank = dist.get_rank()
    world_size = dist.get_world_size()

    # 1. Extract local experts (sharded)
    local_expert_state = {}
    for name, param in model.named_parameters():
        if 'expert_weight' in name:
            # name e.g. "blocks.0.mlp.engine.expert_weight1.0"
            local_expert_state[name] = param.data.cpu()

    # 2. Gather all shards to Rank 0
    gathered_experts = [None] * world_size
    dist.gather_object(local_expert_state, gathered_experts if rank == 0 else None, dst=0)

    if rank == 0:
        # 3. Merge into global state
        full_expert_state = merge_expert_states(gathered_experts)
        
        # 4. Create checkpoint
        checkpoint = {
            'step': step,
            'model_state_dict': model.state_dict(),  # Contains DP params + Rank 0 experts (incomplete)
            'full_expert_state': full_expert_state,  # Contains ALL experts merged
            'optimizer_state_dicts': [opt.state_dict() for opt in optimizers],
            'config': config.to_dict(),
            'ep_world_size': world_size
        }
        torch.save(checkpoint, path)

def merge_expert_states(gathered_list):
    """
    Merges list of dicts {param_name: tensor} into global {param_name: stacked_tensor}.
    Assumes parameter names end in index (e.g. '.0', '.1').
    """
    merged = {}
    # Find all base parameter names (e.g. "blocks.0.mlp.engine.expert_weight1")
    # by stripping the local index suffix
    
    # This requires careful parsing since param names are "weight1.0", "weight1.1" etc.
    # We'll group by the prefix before the final numeric index.
    
    # Simplified Logic:
    # 1. Collect all keys from all gathered dicts
    # 2. Group keys that belong to the same tensor array (e.g. expert_weight1)
    # 3. Sort by rank + local_index -> global_index
    # 4. Stack and save to 'merged'
    
    return merged
```

**Loading (`train.py`)**:
```python
def load_checkpoint_ep(path, model):
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    
    checkpoint = torch.load(path)
    
    if 'full_expert_state' in checkpoint:
        if rank == 0:
            full_expert_state = checkpoint['full_expert_state']
            # Split for current world_size
            shards = split_expert_states(full_expert_state, world_size)
        else:
            shards = None
            
        # Scatter shards to ranks
        my_shard = [None]
        dist.scatter_object_list(my_shard, shards if rank == 0 else None, src=0)
        
        # Load local experts
        for name, tensor in my_shard[0].items():
            model.get_parameter(name).data.copy_(tensor)
            
        # Load DP params (exclude experts from strict load)
        dp_state = {k:v for k,v in checkpoint['model_state_dict'].items() if 'expert_weight' not in k}
        model.load_state_dict(dp_state, strict=False)
```

## 4. Config Schema
Add to `model` config:
```yaml
model:
  expert_parallel: true
```

## 5. Verification
Run `test/test_weight_init.py` with `+model.expert_parallel=True` on 2 GPUs:
- Verify DP params (router, attn) are identical.
- Verify EP params (experts) are different.
