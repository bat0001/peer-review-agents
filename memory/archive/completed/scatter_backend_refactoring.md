# Completed: Engine Refactor with Fused Weighted Scatter

**Completed**: 2025-12-03
**Status**: Implemented and tested

## Summary

Refactored ExpertEngine to return unweighted outputs with separate weights, enabling scatter backends to apply all weights (routed + shared) in a single fused pass.

## Final Architecture

```
ExpertEngine.forward_topk() → gather → expert_fwd → (h_flat, indices, weights_flat, normalizer, metrics)
                                                            ↓
Scatter Backend: applies ALL weights in one fused pass
  - Routed: output[idx] += h_flat[slot] * weights_flat[slot]
  - Shared: output[idx] += shared_flat[idx] * shared_weights[idx]
```

## Key Design Decisions

### 1. Engine Returns 5-tuple (Unweighted)
```python
def forward_topk(self, x, layer_idx, is_shared) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict]:
    """
    Returns:
        h_flat: (E*k, C) UNWEIGHTED expert outputs
        indices_batched: (E, k) token indices
        weights_flat: (E*k,) normalized weights
        normalizer: (N,) per-token normalizer for shared expert
        metrics: routing metrics (for logging only, no tensors for computation)
    """
```

### 2. Fused Weighted Scatter (not add_into)
Instead of pre-weighting h_flat and using `add_into`, scatter backends receive unweighted outputs and apply all weights during aggregation:

```python
# Scatter signature
def __call__(self, h_flat, indices_batched, n_tokens, weights_flat,
             shared_flat=None, shared_weights=None) -> Tensor:
    """
    Applies all weights in one fused pass:
    - Routed: output[idx] += h_flat[slot] * weights_flat[slot]
    - Shared: output[idx] += shared_flat[idx] * shared_weights[idx]
    """
```

### 3. Normalizer as Separate Return Value
`normalizer` is returned as a separate tensor (4th return value), not in `metrics` dict. This keeps `metrics` clean for logging-only data.

## Usage Patterns

### GEC (routed only)
```python
h_flat, indices_batched, weights_flat, _, metrics = self.engine.forward_topk(x, layer_idx, is_shared=False)
output = self.scatter(h_flat, indices_batched, n_tokens, weights_flat)
```

### GEC_shared (routed + shared)
```python
h_flat, indices_batched, weights_flat, normalizer, metrics = self.engine.forward_topk(x, layer_idx, is_shared=True)
shared_flat = self._shared_expert_forward(x_flat)  # unweighted
shared_weights = 1.0 / normalizer
output = self.scatter(h_flat, indices_batched, n_tokens, weights_flat,
                      shared_flat=shared_flat, shared_weights=shared_weights)
```

## Files Modified

| File | Changes |
|------|---------|
| `src/models/engines/engine.py` | Return unweighted h_flat + weights_flat + normalizer (5-tuple) |
| `src/ops/scatter_backends.py` | New signature with weights_flat, shared_flat, shared_weights |
| `src/ops/csr.py` | CSRScatterOp updated for shared params, backward computes shared gradients |
| `src/models/gec.py` | Updated to unpack 5-tuple, pass weights_flat |
| `src/models/gec_shared.py` | Updated to use normalizer directly, pass shared params |
| `benchmark/mlp/forward.py` | Updated to new scatter API |
| `benchmark/mlp/engine_wrapper.py` | Updated to new scatter API |

## Testing

All benchmarks pass with both backends (index_add, CSR) and both configs (GEC, GEC_shared):
- Forward validation: max |Δ| < 2e-3 (expected for bfloat16)
- Backward validation: gradient correctness verified

## Design Rationale

See `memory/design/engine_architecture.md` for detailed rationale on:
- Why unweighted returns + fused scatter
- Why scatter backends as composition (not inheritance)
- How to add new scatter backends
