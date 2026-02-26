# Flat API Design for Expert Engines

## Overview

The flat API unifies the return format of `ExpertEngine` and `ParallelExperts` (EP engine) to handle variable-sized outputs cleanly. This is essential for:
1. **Expert Parallelism**: Each rank processes different numbers of tokens
2. **Threshold routing**: Variable k per expert (not fixed like topk)
3. **Cleaner scatter operations**: No padding waste

## API Specification

Both `forward_topk()` and `forward_threshold()` return:

```python
def forward_topk(x, layer_idx, is_shared) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict]:
    """
    Returns:
        h_flat: (total_active, C)      # Expert outputs, only valid entries
        indices_flat: (total_active,)  # Token indices, flat 1D
        weights_flat: (total_active,)  # Router weights, matches indices
        fanout: (n_tokens,)            # Per-token expert count
        metrics: Dict                  # Routing metrics
    """
```

## Key Design Decisions

### 1. Flat indices instead of batched (E, k)

**Old API**:
```python
indices_batched: (E, k)  # Fixed size, requires padding for threshold mode
weights_flat: (E*k,)     # Includes padding entries (weight=0)
```

**New API**:
```python
indices_flat: (total_active,)  # Variable size, no padding
weights_flat: (total_active,)  # Only valid entries
```

### 2. BMM still uses batched format internally

The expert forward pass requires batched format for `torch.bmm`:
```python
# Internal to engine (not exposed):
x_batched = x_flat[indices_batched]  # (E, k, C)
h_batched = self._batched_expert_forward(x_batched)  # (E, k, C)

# Flatten before return:
h_flat = h_batched[valid_mask.view(-1)]  # (total_active, C)
```

### 3. Extra memory copy is acceptable

Flattening valid entries requires a copy:
```python
h_flat = h_batched.view(-1, C)[valid_mask.view(-1)]
```

This is O(total_active × C), which is smaller than the padded size. The benefits:
- Scatter processes fewer entries
- CSR slot_counts are accurate
- No division by zero from padding indices

## Implementation Details

### ExpertEngine (topk mode)
Topk always has fixed k per expert, so `total_active = E * k`:
```python
indices_flat = indices_batched.reshape(-1)  # Just reshape, no copy
h_flat = h_batched.view(-1, C)              # Just reshape
```

### ExpertEngine (threshold mode)
Variable k per expert, uses valid_mask:
```python
indices_flat = indices_batched[valid_mask]  # Extract valid
weights_flat = weights_batched[valid_mask]
h_flat = h_batched[valid_mask.view(-1)]
```

### ParallelExperts (EP)
Returns naturally flat (each rank has different size):
```python
# local_indices already flat from masking
return expert_outputs_received, local_indices, weights_flat, fanout, metrics
```

## Scatter Backend Changes

### IndexAddScatter
Trivial change - just use flat indices directly:
```python
output.index_add_(0, indices_flat, h_weighted)
```

### CSR Scatter
New `build_slot_indices_flat()` function:
```python
def build_slot_indices_flat(indices_flat, num_tokens, max_experts):
    """Build CSR from flat indices (no E,C structure needed)."""
    sort_idx = torch.argsort(indices_flat, stable=True)
    slot_indices = sort_idx  # Reordering for h_flat
    slot_counts = torch.bincount(indices_flat, minlength=num_tokens)
    slot_offsets = torch.cumsum(slot_counts, dim=0) - slot_counts
    return slot_indices, slot_offsets, slot_counts
```

The Triton kernels themselves are unchanged - they just need the CSR structure.

## Benefits Summary

| Aspect | Old (Batched) | New (Flat) |
|--------|---------------|------------|
| Threshold mode | Padding waste | No waste |
| EP support | Shape mismatch | Natural fit |
| Scatter ops | Processes padding | Only valid |
| CSR counts | Includes padding | Accurate |
| Code clarity | `.view(-1)` everywhere | Clean flat |

## Terminology Note

**Scatter backends** (in this document) refer to output aggregation operations (`index_add_`, CSR scatter) that combine expert outputs back into token order. These are local tensor operations.

This is distinct from **EP dispatch/combine** which are all-to-all communication phases:
- **Dispatch**: Sends tokens to expert-owning ranks
- **Combine**: Returns expert outputs to original ranks

The scatter backends are used *after* the combine phase to aggregate outputs.
