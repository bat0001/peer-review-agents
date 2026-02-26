# Plan: Add softmax_e gating for GEC_shared

## Summary

Add `softmax_e` and `softmax_e_shared_out` router activations with `normalization_mode` config. Refactor to unified activation pattern with new `router_utils.py`.

---

## Background

### Current State

**Router activation flow (old):**
```
router_logits → top-k selection → activation(selected_logits) → weights
```

- `apply_router_activation()` in `RouterMixin` (model_base.py:247-283)
- Called AFTER top-k with only selected logits: `(n_experts, k)`
- Works for sigmoid/relu/softmax_k but NOT softmax_e

**Problem with softmax_e:**
- softmax_e needs softmax over ALL experts per token BEFORE selection
- Then gather weights at selected positions
- Current flow applies activation too late

### Key Files (current state)

| File | Current Role |
|------|-------------|
| `src/models/model_base.py` | Contains `RouterMixin` with `apply_router_activation()` and `compute_fanout()` |
| `src/models/engines/engine.py` | Inherits `RouterMixin`, calls `self.apply_router_activation(topk_values, ...)` at line 152 |
| `src/models/gec_shared.py` | Uses 5-tuple return from engine, applies fanout+1 normalization |
| `src/models/gec.py` | Uses 5-tuple return from engine, applies fanout normalization |
| `src/config.py` | Validates `router_activation` in ["sigmoid", "relu", "softmax_k", "softmax_e", "softmax_e_shared_out"] |

---

## Design: Unified Activation Pattern

### New Flow

```
router_logits → activation(ALL_logits) → top-k selection → gather(weights) → expert_outputs
```

**Key insight:** Apply activation to ALL `(B*T, n_experts)` logits first, then use `torch.gather` to pick weights at selected positions.

### Benefits

1. **Single code path** for all activations (except softmax_k)
2. **Cleaner separation**: activation logic in `router_utils.py`, not in engine
3. **Extensible**: easy to add new activation functions
4. **Removes RouterMixin**: engine no longer needs mixin inheritance

---

## Implementation

### Step 1: Create `src/models/router_utils.py` (NEW FILE)

```python
"""Router activation and utility functions.

This module provides activation functions for MoE routing that operate on
ALL router logits before top-k selection, enabling unified gather-based
weight extraction.
"""
import torch
import torch.nn.functional as F
from torch import Tensor
from typing import Tuple, Optional


def apply_router_activation(
    router_logits: Tensor,
    activation: str,
    G: int = 2
) -> Tuple[Optional[Tensor], Optional[Tensor]]:
    """Apply activation to ALL router logits before top-k selection.

    This unified function handles all activation types. For most activations,
    it computes weights for all (token, expert) pairs, which are later
    gathered at selected positions.

    Args:
        router_logits: (B*T, n_routed_experts) raw router logits
        activation: One of: sigmoid, relu, softmax_k, softmax_e, softmax_e_shared_out
        G: Granularity, used for softmax_e_shared_out (shared weight = 1/G)

    Returns:
        all_weights: (B*T, n_routed_experts) or None
            - For sigmoid/relu/softmax_e*: activated weights for all positions
            - For softmax_k: None (requires top-k positions, handled separately)
        shared_weights: (B*T,) or None
            - For softmax_e: per-token shared expert weight (from softmax with anchor=0)
            - For softmax_e_shared_out: fixed 1/G per token
            - For others: None (shared weight computed via fanout normalization)

    Weight semantics by activation:
        - sigmoid: bounded (0, 1), independent per expert
        - relu: sparse, unbounded positive
        - softmax_k: per-expert normalization (across k selected tokens)
        - softmax_e: per-token normalization (shared IN softmax, anchor=0)
        - softmax_e_shared_out: per-token normalization (shared OUT, fixed 1/G)
    """
    n_tokens = router_logits.shape[0]
    device = router_logits.device
    dtype = router_logits.dtype

    if activation == "sigmoid":
        return torch.sigmoid(router_logits), None

    elif activation == "relu":
        return F.relu(router_logits), None

    elif activation == "softmax_k":
        # softmax_k normalizes across k selected tokens PER EXPERT (dim=-1)
        # This requires knowing which tokens are selected first
        # Return None to signal: handle after top-k selection
        return None, None

    elif activation == "softmax_e":
        # Shared expert IN softmax: compete with routed experts
        # Anchor logit = 0 represents shared expert's "default" contribution
        # Higher routed logits → lower shared weight, lower routed → higher shared
        anchor = torch.zeros(n_tokens, 1, device=device, dtype=dtype)
        augmented = torch.cat([anchor, router_logits], dim=-1)  # (B*T, 1 + n_routed)
        all_w = F.softmax(augmented, dim=-1)
        shared_weights = all_w[:, 0]    # (B*T,) - shared expert weight per token
        routed_weights = all_w[:, 1:]   # (B*T, n_routed) - routed expert weights
        return routed_weights, shared_weights

    elif activation == "softmax_e_shared_out":
        # Shared expert OUT of softmax: anchor normalizes routed, but shared weight is fixed 1/G
        # Anchor logit = 0 "steals" some probability from routed experts
        # But shared expert gets fixed 1/G regardless (doesn't use anchor's probability)
        anchor = torch.zeros(n_tokens, 1, device=device, dtype=dtype)
        augmented = torch.cat([anchor, router_logits], dim=-1)  # (B*T, 1 + n_routed)
        all_w = F.softmax(augmented, dim=-1)
        routed_weights = all_w[:, 1:]   # (B*T, n_routed) - routed weights (sum < 1)
        # Shared weight is FIXED 1/G, not from softmax
        shared_weights = torch.full((n_tokens,), 1.0 / G, device=device, dtype=dtype)
        return routed_weights, shared_weights

    else:
        raise ValueError(f"Unknown router_activation: {activation}")


def compute_fanout(
    n_tokens: int,
    indices: Tensor,
    device: torch.device,
    dtype: torch.dtype
) -> Tensor:
    """Count how many experts selected each token.

    Args:
        n_tokens: Total number of tokens (B*T)
        indices: (total_selected,) flattened token indices from all experts
        device: Output device
        dtype: Output dtype

    Returns:
        fanout: (n_tokens,) count of experts that selected each token
    """
    return torch.bincount(indices, minlength=n_tokens).to(dtype)
```

---

### Step 2: Modify `src/models/engines/engine.py`

**Current signature (line ~85):**
```python
def forward_topk(self, x, layer_idx=0, is_shared=False) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict]:
    # Returns: (h_flat, indices_flat, weights_flat, fanout, metrics)
```

**New signature:**
```python
def forward_topk(self, x, layer_idx=0, is_shared=False) -> Tuple[Tensor, Tensor, Tensor, Tensor, Optional[Tensor], Dict]:
    # Returns: (h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics)
```

**Changes:**

1. **Add import at top:**
```python
from src.models.router_utils import apply_router_activation, compute_fanout
```

2. **Remove RouterMixin inheritance** (line ~40):
```python
# OLD: class ExpertEngine(nn.Module, RouterMixin):
# NEW:
class ExpertEngine(nn.Module):
```

3. **Modify forward_topk (around lines 100-155):**

```python
def forward_topk(self, x: Tensor, layer_idx: int = 0, is_shared: bool = False):
    B, T, C = x.shape
    n_tokens = B * T
    x_flat = x.view(-1, C)

    # Compute router logits
    router_logits_flat = torch.mm(x_flat, self.router_w)  # (B*T, n_routed_experts)

    # Apply activation to ALL logits BEFORE top-k
    # Returns (all_weights, shared_weights) - shared_weights is None for non-softmax_e
    all_weights, shared_weights = apply_router_activation(
        router_logits_flat,
        self.config.router_activation,
        self.config.granularity
    )

    # Compute k (tokens per expert)
    if is_shared:
        # GEC_shared: k = n_tokens × (G-1) / (G × E)
        k = int(n_tokens * (self.config.granularity - 1) //
                (self.config.granularity * self.config.expansion))
    else:
        # GEC: k = n_tokens / E
        k = int(n_tokens // self.config.expansion)
    k = min(k, n_tokens)

    # Top-k selection on RAW logits (not activated weights)
    topk_values, topk_indices = torch.topk(
        router_logits_flat.t(),  # (n_routed_experts, B*T)
        k=k,
        dim=1
    )  # Both: (n_routed_experts, k)

    # Extract cutoffs for threshold routing EMA
    cutoffs = topk_values[:, -1]
    if self.training:
        self.cutoff_accum_sum.add_(cutoffs.detach())
        self.cutoff_accum_count.add_(1)

    # Flatten indices
    indices_batched = topk_indices  # (n_routed_experts, k)
    indices_flat = indices_batched.view(-1)  # (n_routed_experts * k,)

    # Compute weights via gather (unified for most activations)
    if all_weights is not None:
        # Gather pre-computed weights at selected positions
        # all_weights.t(): (n_routed_experts, B*T)
        # topk_indices: (n_routed_experts, k)
        # Result: (n_routed_experts, k) → flatten to (n_routed_experts * k,)
        weights_flat = torch.gather(all_weights.t(), dim=1, index=topk_indices).view(-1)
    else:
        # softmax_k: normalize across k selected tokens per expert
        weights_flat = F.softmax(topk_values, dim=-1).view(-1)

    # Compute fanout
    fanout = compute_fanout(n_tokens, indices_flat, x.device, torch.float32)

    # Expert computation (unchanged)
    h_flat = self._compute_expert_outputs(x_flat, indices_batched)

    # Compute metrics (unchanged)
    metrics = self._compute_metrics(
        router_logits_flat=router_logits_flat,
        indices=indices_flat,
        weights=weights_flat,
        fanout=fanout,
        cutoffs=cutoffs,
        n_tokens=n_tokens,
        layer_idx=layer_idx,
        k_actual=None,
        above_counts=None,
        capacity_config=None
    )

    # Return 6-tuple (added shared_weights)
    return h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics
```

4. **Similarly update `forward_threshold`** to return 6-tuple with `shared_weights`.

---

### Step 3: Modify `src/models/gec_shared.py`

**Current forward (lines 86-154):**
- Receives 5-tuple from engine
- Always applies fanout+1 normalization
- Computes `shared_weights = 1 / (fanout + 1)`

**New forward:**

```python
def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
    B, T, C = x.shape
    n_tokens = B * T
    x_flat = x.view(-1, C)

    # Decide routing mode
    if self.routing_mode is None:
        mode = 'topk' if self.training else 'threshold'
    else:
        mode = self.routing_mode

    # Get routed expert outputs (now 6-tuple with shared_weights)
    if mode == 'topk':
        h_flat, indices_flat, weights_flat, fanout, engine_shared_weights, metrics = \
            self.engine.forward_topk(x, layer_idx, is_shared=True)
    else:
        h_flat, indices_flat, weights_flat, fanout, engine_shared_weights, metrics = \
            self.engine.forward_threshold(x, layer_idx, is_shared=True)

    # Apply normalization based on config
    if self.config.normalization_mode == "fanout":
        # Standard fanout normalization: divide by (fanout + 1)
        one = torch.tensor(1.0, device=fanout.device, dtype=fanout.dtype)
        normalizer = fanout + one  # (B*T,)
        normalizer_flat = normalizer[indices_flat]
        normalized_weights = weights_flat / normalizer_flat
        shared_weights = one / normalizer  # (B*T,)

    elif self.config.normalization_mode == "none":
        # No normalization: use weights as-is
        # For softmax_e variants, weights are already properly normalized
        normalized_weights = weights_flat
        shared_weights = engine_shared_weights  # From engine (softmax or 1/G)

    else:
        raise ValueError(f"Unknown normalization_mode: {self.config.normalization_mode}")

    # Compute shared expert output
    shared_flat = self._shared_expert_forward(x_flat)  # (B*T, C)

    # Scatter: combine routed and shared expert outputs
    output = self.scatter(
        h_flat, indices_flat, n_tokens, normalized_weights,
        shared_flat=shared_flat, shared_weights=shared_weights
    )

    # Update metrics
    metrics = self._update_metrics_with_shared(metrics, n_tokens)

    return output.view(B, T, C).to(x.dtype), metrics
```

**Also add `normalization_mode` to `__init__`** if needed for caching.

---

### Step 4: Modify `src/models/gec.py`

**Change:** Handle 6-tuple return, ignore `shared_weights`.

```python
def forward(self, x: Tensor, layer_idx: int = 0):
    # ...

    # Handle 6-tuple (ignore shared_weights for non-shared model)
    h_flat, indices_flat, weights_flat, fanout, _shared_weights, metrics = \
        self.engine.forward_topk(x, layer_idx, is_shared=False)

    # Rest unchanged...
```

---

### Step 5: Modify `src/models/model_base.py`

1. **Remove `RouterMixin` class entirely** (lines 244-306)

2. **Remove softmax_e validation error** (lines ~93-98):
```python
# DELETE this block:
if self.router_activation == "softmax_e":
    raise ValueError(
        f"router_activation='softmax_e' conflicts with fanout normalization: ..."
    )
```

---

### Step 6: Modify `src/config.py`

**Add `normalization_mode` to model config and validation:**

```python
# In the model config section (around line 254):
# Add after router_activation
normalization_mode: str = "fanout"  # fanout, none

# In __post_init__ validation:
if "normalization_mode" in self.model:
    assert self.model.get("normalization_mode") in ["fanout", "none"], \
        f"Invalid normalization_mode: {self.model.get('normalization_mode')}"

# Enforce softmax_e requires none:
router_act = self.model.get("router_activation", "sigmoid")
norm_mode = self.model.get("normalization_mode", "fanout")
if router_act.startswith("softmax_e") and norm_mode != "none":
    raise ValueError(
        f"router_activation='{router_act}' requires normalization_mode='none', "
        f"got '{norm_mode}'"
    )
```

---

### Step 7: Modify `src/models/engines/parallel_experts_manual.py`

Same pattern as `engine.py`:
1. Import from `router_utils`
2. Remove `RouterMixin` inheritance
3. Update `forward_topk` and `forward_threshold` to return 6-tuple
4. Use `apply_router_activation` + gather pattern

---

## Files to Modify

| File | Change |
|------|--------|
| `src/models/router_utils.py` | **NEW**: `apply_router_activation()`, `compute_fanout()` |
| `src/models/engines/engine.py` | Import router_utils, remove RouterMixin, unified gather, return 6-tuple |
| `src/models/engines/parallel_experts_manual.py` | Same pattern as engine.py |
| `src/models/gec_shared.py` | Handle 6-tuple, use `normalization_mode` config |
| `src/models/gec.py` | Handle 6-tuple (ignore shared_weights) |
| `src/models/model_base.py` | **Remove RouterMixin entirely**, remove softmax_e validation |
| `src/config.py` | Add `normalization_mode` config + validation |
| `configs/mlp/gec_shared.yaml` | Document `normalization_mode` option |

---

## Activation Summary Table

| Activation | all_weights | shared_weights | normalization_mode | Notes |
|------------|-------------|----------------|-------------------|-------|
| `sigmoid` | sigmoid(logits) | None | fanout (default) or none | Independent weights |
| `relu` | relu(logits) | None | fanout (default) or none | Sparse weights |
| `softmax_k` | None | None | fanout (default) | Per-expert normalization |
| `softmax_e` | softmax(aug)[:, 1:] | softmax(aug)[:, 0] | **none required** | Shared IN softmax |
| `softmax_e_shared_out` | softmax(aug)[:, 1:] | 1/G fixed | **none required** | Shared OUT, anchor normalizes routed |

---

## Testing

1. **Existing tests pass**: `router_activation=sigmoid normalization_mode=fanout` (default)
2. **softmax_e**: `router_activation=softmax_e normalization_mode=none`
   - Verify: sum of (shared_weight + selected_routed_weights) ≤ 1.0 per token
3. **softmax_e_shared_out**: `router_activation=softmax_e_shared_out normalization_mode=none`
   - Verify: shared_weight = 1/G constant, routed weights sum < 1
4. **sigmoid+none**: `router_activation=sigmoid normalization_mode=none`
   - Verify: no normalization applied
5. **Training run**: Compare loss curves across activation types
