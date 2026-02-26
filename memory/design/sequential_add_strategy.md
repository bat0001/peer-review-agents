# Sequential Add Strategy: Bandwidth-Optimal MoE Recombination

**Created**: 2025-12
**Status**: Implemented
**Implementation**: `src/kernels/sequential.py`, `src/kernels/sequential2.py`

## Core Problem

Expert outputs are **partitioned by expert** `[E, k, H]`, but recombination requires **grouping by token** `[N, H]`. Naive approaches fail:
- `torch.index_add`: atomic contention when multiple experts write to same token
- Direct per-token reduction: random access to `expert_out` → poor cache behavior
- Padding to fixed experts/token: wastes bandwidth on zeros

## Solution: Global Sort + Sequential Add

Key insight: **Index manipulation is negligible** compared to moving H-dimensional vectors.

### Algorithm
1. Build global assignment list: `(token_id, expert_id, local_idx)` triples
2. Sort by `token_id` → all contributions for each token are contiguous
3. Launch token-parallel kernel that reduces contiguous segments

### Performance Characteristics
| Metric | Value |
|--------|-------|
| Memory reads | E×k×H (expert outputs) - **once** |
| Memory writes | N×H (final output) - **once** |
| Index overhead | 3×E×k ints → negligible (<0.1ms sort) |
| Atomic contention | Zero |

This is **bandwidth-optimal** — cannot do better than reading each vector once.

## Data Structures

### Inverse Index Formats

**Dense format** (`sequential.py`):
- Shape: `(N, MAX_EXPERTS)` with -1 padding
- Simple but uses more memory

**CSR-style format** (`sequential2.py`):
- `inverse_indices`: flat array of (expert_id, local_idx) pairs
- `index_offsets`: prefix sum per token
- `expert_counts`: number of contributing experts per token
- More memory-efficient for variable fanout

## Implementation Details

### Token-Parallel Kernel Pattern
```python
# One thread per token
token_id = tl.program_id(0)
start = token_start[token_id]
end = token_start[token_id + 1]

# Register accumulator
acc = tl.zeros((H,), dtype=tl.float32)

# Loop over contributions (MAX_EXPERTS is small, ~16)
for i in range(MAX_EXPERTS):
    if i >= (end - start):
        break
    expert_id = sorted_expert_id[start + i]
    local_idx = sorted_local_idx[start + i]
    acc += expert_out[expert_id, local_idx, :]

output[token_id] = acc
```

### Why This Works
- **No data movement**: `expert_out` stays in original layout
- **One-read guarantee**: Sorted indices enumerate each output exactly once
- **Contiguous reduction**: Per-token contributions at `[start, end)` — perfect for loop
- **Leverages per-expert sort**: Cache-friendly during flat array construction

## Design Decisions

1. **Sort cost is acceptable**: 256k int32 sort < 0.1ms vs 1+ ms for vector movement
2. **Register accumulation**: No shared memory needed for small MAX_EXPERTS (≤16)
3. **FP32 accumulation**: Numerical stability, store as BF16
4. **Token-parallel not slot-parallel**: One thread per token, loop over experts
