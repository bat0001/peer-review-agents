# Plan: Enable Expert Parallel (EP) for GEC (no shared expert)

## Goal
Allow `model_type=gec` to run with `expert_parallel=true` (EP), while adding explicit safety checks for multi-GPU + expert sharding invariants. Keep behavior for `gec_shared` unchanged.

## Current State (confirmed in code)
- `src/config.py` hard-blocks EP unless `model_type == 'gec_shared'`.
- `src/models/gec.py` already routes EP through `ParallelExperts` when `config.expert_parallel` is true.
- `src/models/engines/parallel_experts_manual.py` implements top-k and threshold routing for `is_shared=False`, but assumes `n_routed_experts % world_size == 0` (no guard) and requires distributed init.

## Proposed Changes (tactical)
1) **Relax config validation** to allow EP for `model_type` in `{gec, gec_shared}` and update error messaging.
2) **Add fail-fast guards** in `ParallelExperts.__init__`:
   - `dist.is_initialized()` must be true when EP is enabled.
   - `n_routed_experts % world_size == 0` must hold; otherwise raise a clear `ValueError`.
3) **Update EP comment** in `configs/config.yaml` to clarify supported model types (optional but low risk).
4) **(Optional) Extend EP init test** to cover `gec` alongside `gec_shared`.

## Broader Refactor Option (non-blocking)
Create a single `validate_expert_parallel(config, world_size)` helper (e.g., in `src/utils/distributed.py` or a new validation module) used by both config validation and `ParallelExperts` to avoid duplicated checks. This would be a follow-up refactor; the tactical change above is smaller and safer.

---

## File-by-File Plan + Snippets

### 1) `src/config.py`
**Why:** Unblock `gec` + EP at config validation time.

**Current snippet** (validation block):
```python
model_type = self.model.get("model_type")
if self.model.get("expert_parallel", False) and model_type != "gec_shared":
    raise ValueError("expert_parallel is only supported for model_type='gec_shared'")
```

**Planned change:**
```python
model_type = self.model.get("model_type")
if self.model.get("expert_parallel", False) and model_type not in ["gec", "gec_shared"]:
    raise ValueError("expert_parallel is only supported for model_type in ['gec', 'gec_shared']")
```

### 2) `src/models/engines/parallel_experts_manual.py`
**Why:** Fail fast with clearer errors for EP configuration issues.

**Current snippet** (near `__init__`):
```python
self.world_size = dist.get_world_size()
self.rank = dist.get_rank()
self.local_experts = n_routed_experts // self.world_size
```

**Planned change:**
```python
if not dist.is_initialized():
    raise RuntimeError("Expert parallelism requires torch.distributed to be initialized (use torchrun).")
self.world_size = dist.get_world_size()
self.rank = dist.get_rank()
if n_routed_experts % self.world_size != 0:
    raise ValueError(
        f"n_routed_experts ({n_routed_experts}) must be divisible by world_size ({self.world_size}) for EP"
    )
self.local_experts = n_routed_experts // self.world_size
```

### 3) `configs/config.yaml` (optional)
**Why:** Make the EP support scope explicit in the base config comment.

**Current snippet:**
```yaml
  expert_parallel: false  # EP mode: shard experts across GPUs (requires multi-GPU)
```

**Planned change:**
```yaml
  expert_parallel: false  # EP mode: shard experts across GPUs (gec/gec_shared only; requires multi-GPU)
```

### 4) `test/test_ep_init.py` (optional)
**Why:** Ensure EP init logic works for both `gec` and `gec_shared` (same DP/EP split).

**Current snippet** (single model_type):
```python
config = ModelConfig(
    n_embd=256,
    n_layer=2,
    n_head=4,
    model_type="gec_shared",
    granularity=2,
    expansion=4,
    expert_parallel=True,
)
```

**Planned change (example):**
```python
for model_type in ["gec", "gec_shared"]:
    config = ModelConfig(
        n_embd=256,
        n_layer=2,
        n_head=4,
        model_type=model_type,
        granularity=2,
        expansion=4,
        expert_parallel=True,
    )
    # create model and run the same checks
```

---

## Validation Plan (post-approval)
- **Unit:** `torchrun --nproc_per_node=2 test/test_ep_init.py` (if we extend it to cover `gec`).
- **Smoke (optional):** `torchrun --nproc_per_node=2 train.py mlp=gec +experiment=debug model.expert_parallel=true` with small batch/steps.
- Verify: no config validation error, EP initialization succeeds, router + non-expert weights are DP-synced, expert weights are rank-divergent.

## Risk/Notes
- EP requires distributed launch; we’ll make the error explicit rather than allowing an opaque `dist.get_world_size()` failure.
- `n_routed_experts % world_size == 0` is a hard constraint for current EP routing layout.
- This change doesn’t alter routing math; it only unblocks GEC + EP and improves guardrails.
