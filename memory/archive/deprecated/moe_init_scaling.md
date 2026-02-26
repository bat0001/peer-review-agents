# MoE Initialization Scaling Plan

> **DEPRECATED** (2025-12): Superseded by unified aspect-ratio Kaiming initialization. See `memory/design/initialization.md`.

**Status:** Proposed (not yet implemented)
**Created:** 2025-10-17
**Motivation:** Scale MoE expert weight initialization by `1/sqrt(E)` to maintain similar gradient magnitudes as number of experts grows.

## Background

Currently, all MoE expert parameters are initialized with `std=0.02` (matching GPT-2 dense model initialization). As the expansion factor `E` increases, the total parameter count and gradient flow changes, which may require scaled initialization.

### Current Initialization

All MoE variants use inline initialization in `__init__`:

```python
self.router_w = nn.Parameter(torch.randn(config.n_embd, config.n_experts) * 0.02)
self.weight1 = nn.Parameter(torch.randn(config.n_experts, config.expert_dim, config.n_embd) * 0.02)
self.weight2 = nn.Parameter(torch.randn(config.n_experts, config.n_embd, config.expert_dim) * 0.02)
```

**Key insight:** These are raw `nn.Parameter` objects, NOT `nn.Linear` modules. Therefore, they are **not affected** by `BaseGPT._init_weights()` which only handles `nn.Linear` and `nn.Embedding`. The inline initialization is what's actually used.

### Affected Files

All MoE implementations:
- `src/models/gec/gec.py` (GECMLP)
- `src/models/gec/reference.py` (GECMLPReference)
- `src/models/gec/triton.py` (GECTritonMLP)
- `src/models/gec/triton1.py` (GECTriton1MLP)
- `src/models/gec/segmented.py` (GECSegmentedMLP)
- `src/models/gec_shared/shared.py` (GECSharedMLP)
- `src/models/ec.py` (ECMLP)

## Proposed Change

### Formula

For MoE expert linear layers (`weight1`, `weight2`):
```python
std = 0.02 / sqrt(E)
```

where `E = config.expansion`.

### Parameters to Scale

**DO scale:**
- `weight1` (first expert linear layer)
- `weight2` (second expert linear layer)

**DO NOT scale:**
- `router_w` (router stays at std=0.02)
- `bias1`, `bias2` (biases stay at zero)

**Open question:**
- Should `shared_weight1` and `shared_weight2` in GECSharedMLP be scaled, or stay at 0.02?
  - Argument for scaling: Consistency with routed experts
  - Argument against: Shared expert always processes all tokens (different behavior)

### Rationale

1. **Variance scaling:** With E experts, each processing ~1/E of tokens, total gradient contribution scales differently
2. **Consistent magnitude:** Scaling by `1/sqrt(E)` maintains similar activation and gradient magnitudes across different expansion factors
3. **Standard practice:** Similar to width scaling in dense networks (e.g., attention heads, FFN dimension)

## Implementation Options

### Option 1: Centralized Helper Method (Recommended)

Add a helper method to `BaseMLP` class:

```python
class BaseMLP(nn.Module, ABC):
    def _get_expert_std(self, std_base: float = 0.02) -> float:
        """Get scaled std for expert weight initialization.

        Returns std = std_base / sqrt(E) where E is the expansion factor.
        Router weights do not use this scaling.
        """
        import math
        return std_base / math.sqrt(self.config.expansion)
```

Each MoE class uses it in `__init__`:

```python
def __init__(self, config: ModelConfig):
    super().__init__(config)

    expert_std = self._get_expert_std()

    # Router: keep at 0.02 (no scaling)
    self.router_w = nn.Parameter(torch.randn(config.n_embd, config.n_experts) * 0.02)

    # Expert weights: use scaled std
    self.weight1 = nn.Parameter(torch.randn(config.n_experts, config.expert_dim, config.n_embd) * expert_std)
    self.bias1 = nn.Parameter(torch.zeros(config.n_experts, config.expert_dim))

    self.weight2 = nn.Parameter(torch.randn(config.n_experts, config.n_embd, config.expert_dim) * expert_std)
    self.bias2 = nn.Parameter(torch.zeros(config.n_experts, config.n_embd))
```

**Pros:**
- Single source of truth for the scaling formula
- Easy to change formula later
- Clear naming (`_get_expert_std()` makes intent obvious)
- Minimal code changes (just replace `0.02` with `expert_std` for expert weights)

**Cons:**
- Need to remember to use it (but only 7 files to update)

### Option 2: Inline Calculation

Directly compute in each `__init__`:

```python
import math
expert_std = 0.02 / math.sqrt(self.config.expansion)
```

**Pros:**
- Very explicit
- No new abstractions

**Cons:**
- Duplicated formula across 7 files
- Harder to update if formula changes

### Option 3: No Refactoring - Just Replace

Simply replace `* 0.02` with `* (0.02 / math.sqrt(config.expansion))` for expert weights.

**Pros:**
- Minimal change
- No new methods

**Cons:**
- Formula duplicated everywhere
- Less maintainable

## Recommended Approach

**Use Option 1** - Add `_get_expert_std()` helper to `BaseMLP`:

1. **Step 1:** Add helper method to `BaseMLP` in `src/models/model_base.py`
2. **Step 2:** Update each MoE `__init__` to:
   - Call `expert_std = self._get_expert_std()` at the top
   - Use `expert_std` for `weight1` and `weight2` initialization
   - Keep router at `0.02`
3. **Step 3:** Decide on shared expert scaling for GECSharedMLP

## Implementation Checklist

- [ ] Add `_get_expert_std()` to `BaseMLP` in `src/models/model_base.py`
- [ ] Update `src/models/gec/gec.py`
- [ ] Update `src/models/gec/reference.py`
- [ ] Update `src/models/gec/triton.py`
- [ ] Update `src/models/gec/triton1.py`
- [ ] Update `src/models/gec/segmented.py`
- [ ] Update `src/models/ec.py`
- [ ] Update `src/models/gec_shared/shared.py` (decide on shared expert scaling)
- [ ] Test training convergence with new initialization
- [ ] Compare initial loss/gradients with old vs new initialization

## Open Questions

1. **Shared expert in GECSharedMLP:** Should it use scaled std or stay at 0.02?
2. **Experimental validation:** Should we A/B test the initialization change to verify it improves training?
3. **Backward compatibility:** Do we care about loading old checkpoints? (Project guidelines say "no backward compatibility")

## Notes

- This follows project guideline: "Consider refactoring the larger system to make it more maintainable"
- The `_get_expert_std()` helper keeps the formula in one place for future changes
- Router weights intentionally NOT scaled - they're selecting tokens, not transforming representations
