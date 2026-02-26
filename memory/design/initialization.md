# Weight Initialization Design

**Date:** 2025-10-27 (Updated: 2025-12-09)
**Status:** Active
**Location:** `src/models/model_base.py:429-511`, `src/utils/distributed.py:86-120`

## Overview

All model weights initialized using **property-based initialization** with aspect-ratio scaled initialization for all linear projections (2D/3D). Supports both Data Parallel (DP) and Expert Parallel (EP) modes.

## Design Principles

### 1. Property-Based Initialization

**Core idea:** Initialize parameters based on their **properties** (dimensions, role) rather than their module type.

**Why:**
- Handles both `nn.Module` weights and raw `nn.Parameter` uniformly
- Works with expert weight ParameterLists (2D parameters)
- Single source of truth for all initialization logic
- Fails loudly on unexpected parameters

### 2. Aspect-Ratio Scaled Kaiming

**Formula:**
```python
std = 1.0 / sqrt(fan_in) * min(1.0, sqrt(fan_out / fan_in))
```

**Components:**
- `1.0 / sqrt(fan_in)` - Standard Kaiming He initialization
- `min(1.0, sqrt(fan_out / fan_in))` - Aspect ratio correction

**Purpose:**
- Maintains variance when fan_out ≠ fan_in
- Prevents exploding activations in unbalanced layers
- nanochat style initialization

**Applied to:**
- All attention weights (2D)
- All MLP weights (2D, including expert ParameterLists)
- Router weights (2D)
- Both routed and shared expert weights

### 3. Special Cases

| Parameter Type | Initialization | Reason |
|---------------|----------------|--------|
| **Embeddings** | `Normal(0, 1.0)` | Standard embedding init |
| **Output projections** (`lm_head`, `c_proj`, `*weight2`) | `Zero` | Required for Muon optimizer |
| **Router weights** | `Normal(0, 1/√fan_in)` | Small init for symmetry breaking |
| **All other weights** | Aspect-ratio scaled | Principled variance preservation |
| **Biases** | `Zero` | Standard (though nanochat avoids biases) |

**Note:** Router uses simple `1/√fan_in` (not aspect-ratio scaled) because zero init would prevent expert specialization.

**Note (2025-12-13):** Expert output projections (`expert_weight2`, `shared_weight2`) are now zero-initialized like `c_proj`, matching nanochat's pattern for all output projections.

### 4. Verification

**Every `init_weights()` call:**
1. Tracks which parameters were initialized (via `id()`)
2. Verifies ALL parameters in `self.parameters()` were initialized
3. Raises `RuntimeError` if any parameter missed
4. Asserts output projections are actually zero (for Muon)

**Why:** Silent initialization failures are catastrophic (see `memory/testing/weight_initialization.md`).

## Implementation

### nanochat Pattern

**Critical sequence:**
```python
from src.utils.distributed import compute_init, init_model_weights

# 1. Initialize compute (EP mode uses rank-specific seeds)
ddp, rank, local_rank, world_size, device = compute_init(
    seed=42, expert_parallel=config.model.expert_parallel
)

# 2. Create model on meta device (fast allocation)
with torch.device("meta"):
    model = BaseGPT(config)

# 3. Allocate uninitialized tensors on actual device
model.to_empty(device=device)

# 4. Initialize weights (unified entry point for DP/EP)
init_model_weights(model, expert_parallel=config.model.expert_parallel)
```

**Why this matters:**
- `to_empty()` allocates memory but **discards any existing values**
- Any initialization in `__init__` is **thrown away**
- All initialization must happen in `init_weights()`, called **after** `to_empty()`
- For EP mode, `init_model_weights()` broadcasts DP params from rank 0

### Initialization Logic

```python
def init_weights(self):
    """Initialize all weights based on properties with verification."""
    initialized = set()

    for name, param in self.named_parameters():
        # 1. Embeddings
        if 'wte.weight' in name or 'wpe.weight' in name:
            torch.nn.init.normal_(param, mean=0.0, std=1.0)
            initialized.add(id(param))

        # 2. Output projections (zero for Muon)
        # Includes: lm_head, c_proj, expert_weight2, shared_weight2
        elif 'lm_head.weight' in name or 'c_proj.weight' in name or 'weight2' in name:
            torch.nn.init.zeros_(param)
            initialized.add(id(param))

        # 3. Router (small init for symmetry breaking)
        elif 'router.weight' in name:
            std = 1.0 / math.sqrt(param.shape[1])  # 1/√fan_in
            torch.nn.init.normal_(param, mean=0.0, std=std)
            initialized.add(id(param))

        # 4. All other weight matrices (2D/3D)
        elif 'weight' in name:
            if param.dim() == 2:
                fan_out, fan_in = param.shape
            elif param.dim() == 3:  # Expert weights: (n_experts, fan_out, fan_in)
                fan_out, fan_in = param.shape[1], param.shape[2]
            else:
                raise RuntimeError(f"Unexpected weight dimension: {name}")

            std = 1.0 / math.sqrt(fan_in) * min(1.0, math.sqrt(fan_out / fan_in))
            torch.nn.init.normal_(param, mean=0.0, std=std)
            initialized.add(id(param))

        # 5. Biases (shouldn't exist in nanochat style)
        elif 'bias' in name:
            torch.nn.init.zeros_(param)
            initialized.add(id(param))

        else:
            raise RuntimeError(f"Unhandled parameter: {name}")

    # Verify all parameters initialized
    all_params = set(id(p) for p in self.parameters())
    if initialized != all_params:
        raise RuntimeError("Initialization incomplete!")

    # RoPE embeddings (separate from parameters)
    # ... precompute and copy ...

    # Verify zero-init worked
    assert self.lm_head.weight.norm() < 1e-6
```

## Expert Parallel (EP) Mode

### Problem

In EP mode, expert weights are sharded across GPUs (each rank owns different experts). This requires:
- **DP params** (router, attention, embeddings, shared_weight) → **identical** across ranks
- **EP params** (expert_weight) → **different** per rank

With the same seed on all ranks, all expert weights would be identical (wrong).

### Solution: Seed & Broadcast

1. **Rank-specific seeds:** `compute_init(expert_parallel=True)` uses `seed + rank`
2. **Initialize all params divergently:** Each rank gets unique weights
3. **Broadcast DP params:** `broadcast_dp_params()` syncs DP params from rank 0, leaving EP params divergent

```python
# In src/utils/distributed.py

def init_model_weights(model, expert_parallel: bool = False):
    """Unified init entry point for DP/EP modes."""
    model.init_weights()

    if expert_parallel and is_ddp():
        broadcast_dp_params(model)

def broadcast_dp_params(model):
    """Broadcast DP params from rank 0. Skip EP expert weights."""
    for name, param in model.named_parameters():
        if 'expert_weight' in name:
            continue  # EP: keep divergent
        dist.broadcast(param.data, src=0)

    for name, buffer in model.named_buffers():
        if buffer is not None:
            dist.broadcast(buffer, src=0)
```

### Parameter Classification

| Pattern | Type | After Init | After Broadcast |
|---------|------|------------|-----------------|
| `wte.weight` | DP | Divergent | Synced from rank 0 |
| `lm_head.weight` | DP | Divergent | Synced from rank 0 |
| `*.c_proj.weight` | DP | Divergent | Synced from rank 0 |
| `*.router.weight` | DP | Divergent | Synced from rank 0 |
| `shared_weight*` | DP | Divergent | Synced from rank 0 |
| `expert_weight*` | **EP** | **Divergent** | **Remains different** |
| `cutoff_ema` (buffer) | DP | Divergent | Synced from rank 0 |

### Testing

**Test:** `test/test_ep_init.py`

Run with: `torchrun --nproc_per_node=2 test/test_ep_init.py`

Verifies:
- All DP params/buffers identical across ranks
- All EP params different across ranks

## Expert Weight Handling

### Why 2D ParameterLists

Expert weights are stored as **ParameterList of 2D tensors**:
```python
expert_weight1: ParameterList([
    Parameter(expert_dim, n_embd),  # Expert 0 up projection
    Parameter(expert_dim, n_embd),  # Expert 1 up projection
    ...
])
expert_weight2: ParameterList([
    Parameter(n_embd, expert_dim),  # Expert 0 down projection
    Parameter(n_embd, expert_dim),  # Expert 1 down projection
    ...
])
```

**Benefits of 2D ParameterList:**
- Each expert gets separate parameter object → per-expert optimizer states (e.g., Muon)
- PyTorch natively saves/loads ParameterLists as `expert_weight1.0`, `expert_weight1.1`, etc.
- During forward pass, we stack them into 3D tensors for batched computation
- Simpler code: no custom state_dict conversion needed

### Initialization

**Same formula as all 2D weights:**
```python
fan_out, fan_in = param.shape[0], param.shape[1]
std = 1.0 / sqrt(fan_in) * min(1.0, sqrt(fan_out / fan_in))
```

**For tiny model (expert_dim=1024, n_embd=512):**
- `expert_weight1[i]` (1024, 512): `std = 0.0442`
- `expert_weight2[i]` (512, 1024): `std = 0.0221`

**Shared expert weights follow same logic** (also 2D).

## Historical Context

### Original Bug (Pre-2025-10-27)

Expert weights initialized in `__init__`:
```python
self.weight1 = nn.Parameter(torch.randn(...) * 0.02)
```

**Problem:** `to_empty()` discarded these values, left weights at zero.

**Why it happened:**
- Standard modules initialized by `apply()` in `init_weights()`
- Expert Parameters not visited by `apply()`
- No verification that all parameters initialized

### Original Design (Hardcoded 0.02)

Even without the bug, original design used:
- Expert weights: `std = 0.02` (hardcoded)
- Router weights: aspect-ratio scaled
- Other weights: aspect-ratio scaled

**Inconsistency:** No principled reason for experts to differ.

### Current Design (Unified Scaling)

**All weights use aspect-ratio scaled Kaiming:**
- Consistent initialization across all linear projections
- Principled variance preservation
- Expert weights scale with their dimensions

## Output Projection Zero-Init

### Why Zero?

**Muon optimizer requirement:** Muon is designed for training matrix parameters from scratch. Pre-initialized matrices can cause instability.

**What gets zero-initialized:**
- `lm_head.weight` - Final output projection to vocabulary
- All `c_proj.weight` - Attention and MLP output projections

### Verification

**Every `init_weights()` checks:**
```python
lm_head_norm = self.lm_head.weight.norm().item()
assert lm_head_norm < 1e-6, f"lm_head should be zero-initialized"
```

**Why verify:** Zero-init is critical for Muon. If it fails silently, training will be unstable.

## RoPE Embeddings

**Not parameters, but buffers:**
```python
self.register_buffer('cos', ...)
self.register_buffer('sin', ...)
```

**Initialized separately:**
- Precomputed using cos/sin formulas
- Must be on actual device (not meta)
- Updated after parameter initialization

## Testing

**Critical test:** `test/test_weight_init.py`

**Verifies:**
1. All parameters finite (no NaN/Inf)
2. Actual std matches expected std
3. Expert weights properly initialized
4. Output projections are zero

**See:** `memory/testing/weight_initialization.md` for full details.

## Design Alternatives Considered

### 1. Module-Based (apply())

**Idea:** Keep using `apply()`, make MLPs report expert parameters.

**Rejected:**
- Requires adding interface methods to all MLP classes
- Doesn't handle verification
- More complex than property-based approach

### 2. Hardcoded 0.02 for Experts

**Idea:** Keep expert weights at fixed small scale.

**Rejected:**
- No theoretical justification
- Inconsistent with other weights
- Aspect-ratio scaling is more principled

### 3. Custom nn.Module for Expert Weights

**Idea:** Wrap expert weights in custom module to work with `apply()`.

**Rejected:**
- Adds complexity for no benefit
- Property-based approach handles ParameterLists naturally
- Property-based approach simpler

## Future Considerations

### Potential Improvements

1. **Distribution verification:** Test full distribution, not just std
2. **Correlation checks:** Ensure expert weights uncorrelated
3. **Scale experiments:** Try different scaling schemes for experts
4. **Orthogonal init:** Consider orthogonal initialization for some weights

### Known Limitations

1. **Name-based special cases:** Embeddings and outputs identified by name
2. **Dimension assumptions:** Assumes 2D weights, may need update for new architectures
3. **Fixed aspect-ratio formula:** Could be made configurable

## References

- Implementation: `src/models/model_base.py:429-511`
- EP support: `src/utils/distributed.py:86-120`
- Test (general): `test/test_weight_init.py`
- Test (EP): `test/test_ep_init.py`
- Bug documentation: `memory/testing/weight_initialization.md`
- nanochat pattern: https://github.com/karpathy/nanochat
