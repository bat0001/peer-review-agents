# Gate Activation + Normalization Design

**Status**: Implemented (2025-12-17)

## Context

Global Expert Choice (GEC) reorganizes an FFN with granularity \(G\) into \(G \times E\) experts. Top-\(k\) selection uses raw router logits; activations only adjust magnitudes, not assignments.

## Unified Activation Pattern

**Key insight**: ALL activations are applied to ALL logits BEFORE top-k selection, then weights are gathered at selected positions.

**Implementation**: `src/models/router_utils.py`

```python
def apply_router_activation(router_logits, activation, G) -> Tuple[all_weights, shared_weights]:
    """Apply activation to ALL router logits before top-k selection."""
```

**Flow**:
```
router_logits → activation(ALL logits) → top-k selection → gather(weights) → expert_outputs
```

## Activation Types

| Activation | Formula | Normalization Dim | Returns |
|------------|---------|-------------------|---------|
| `sigmoid` | `sigmoid(logits)` | Independent | `(all_weights, None)` |
| `relu` | `relu(logits)` | Independent | `(all_weights, None)` |
| `softmax_k` | `softmax(logits, dim=0)` | Across ALL tokens per expert | `(all_weights, None)` |
| `softmax_e` | `softmax([0, logits], dim=-1)` | Across experts per token | `(routed_weights, shared_weights)` |
| `softmax_e_shared_out` | Same + fixed 1/G | Across experts per token | `(routed_weights, 1/G)` |

### softmax_e Details

Shared expert IN softmax with anchor logit=0:
```python
anchor = zeros(B*T, 1)
augmented = cat([anchor, router_logits], dim=-1)  # (B*T, n_routed+1)
all_w = softmax(augmented, dim=-1)
shared_weights = all_w[:, 0]   # Shared expert weight from softmax
routed_weights = all_w[:, 1:]  # Routed expert weights
```

### softmax_e_shared_out Details

Shared expert OUT of softmax, but anchor still normalizes routed:
```python
anchor = zeros(B*T, 1)
augmented = cat([anchor, router_logits], dim=-1)
all_w = softmax(augmented, dim=-1)
routed_weights = all_w[:, 1:]    # Routed weights (sum < 1 due to anchor)
shared_weights = 1.0 / G         # Fixed weight (e.g., 0.5 for G=2)
```

## Normalization Modes

**Config**: `model.normalization_mode` (default: `fanout`)

| Mode | Description | Use with |
|------|-------------|----------|
| `fanout` | Divide by expert count per token (+1 for shared) | sigmoid, relu, softmax_k |
| `none` | No normalization, use weights as-is | softmax_e, softmax_e_shared_out |

**Validation**: Config raises `ValueError` if softmax_e variants used with non-none normalization.
**Note**: For GEC_shared with `normalization_mode=none` and non-softmax activations,
the shared expert uses weight 1.0 (unweighted). GEC also supports `normalization_mode=none`
and will use raw routed weights as-is.

## Engine Return Signature

Engines return 6-tuple: `(h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics)`

- `shared_weights`: `(B*T,)` for softmax_e variants, `None` otherwise
- GEC_shared uses `shared_weights` when `normalization_mode=none`; if `None`, it
  falls back to shared weight = 1.0
- GEC ignores `shared_weights` (no shared expert)

## Files

| File | Role |
|------|------|
| `src/models/router_utils.py` | `apply_router_activation()`, `compute_fanout()` |
| `src/models/engines/engine.py` | ExpertEngine with 6-tuple return |
| `src/models/engines/parallel_experts_manual.py` | EP version, same pattern |
| `src/models/gec_shared.py` | Handles `normalization_mode` config |
| `src/models/gec.py` | Handles `normalization_mode` (fanout/none), ignores shared_weights |

## Usage

```bash
# Default (sigmoid + fanout normalization)
python train.py mlp=gec_shared

# softmax_e (shared expert IN softmax competition)
python train.py mlp=gec_shared model.router_activation=softmax_e model.normalization_mode=none

# softmax_e with GEC (no shared expert, raw routed weights)
python train.py mlp=gec model.router_activation=softmax_e model.normalization_mode=none

# softmax_e_shared_out (shared expert gets fixed 1/G weight)
python train.py mlp=gec_shared model.router_activation=softmax_e_shared_out model.normalization_mode=none
```

## Comparison

| Aspect | sigmoid+fanout | softmax_e | softmax_e_shared_out |
|--------|----------------|-----------|----------------------|
| Shared weight | 1/(fanout+1) | From softmax | Fixed 1/G |
| Routed weights | sigmoid/fanout | From softmax | From softmax |
| Weight range | (0, 1) | (0, 1) | (0, 1) |
| Shared competes | Via normalization | Yes (in softmax) | No |
