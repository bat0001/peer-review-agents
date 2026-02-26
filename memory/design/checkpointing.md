# Checkpointing Invariants

## Expert Parallel (EP)

EP checkpoints must store **contiguous per-layer expert indices**:
`expert_weight{1,2}.0 .. n_routed_experts-1`.

**Required invariant**
- `local_experts = n_routed_experts // world_size` (derived from config, not from
  key counts in the state_dict).

**Why this matters**
- Non-EP analysis/eval uses strict `load_state_dict`; gapped indices break loading.

**Legacy repair**
- Use `script/archived/fix_ep_checkpoint_indices.py` to rewrite gapped indices to be contiguous
  and save `*_fixed.pt`.
