# Prealloc All-to-All: Zero-Copy Expert Dispatch

**Created**: 2025-12
**Status**: Implemented
**Implementation**: `src/ops/prealloc_all_to_all.py`

## Problem

In Expert Parallelism, the per-expert all-to-all loop has unnecessary memory copies:

```python
# Current: 3 copies
for i in range(local_experts):
    tokens_to_send = x_flat[indices].contiguous()  # Copy 1 - UNAVOIDABLE
    received = all_to_all(tokens_to_send, ...)     # Copy 2 - allocates new buffer
    received_tokens_list.append(received)
tokens_received = torch.stack(received_tokens_list) # Copy 3 - stacks into new
```

## Solution: PreallocAllToAllOp

Custom autograd function that:
1. Takes pre-allocated output buffer
2. Writes all experts' data directly into buffer slices
3. Returns buffer WITH autograd graph attached

### Key Insight

Naive `out=buffer[i]` doesn't work because autograd attaches to returned tensor, not pre-allocated buffer. Solution: wrap entire batched operation in one `autograd.Function`.

## API

```python
def prealloc_all_to_all(
    x_list: List[Tensor],           # Inputs per local expert
    output_splits_list: List[List[int]],
    input_splits_list: List[List[int]],
    recv_offsets: Optional[List[int]] = None,  # None = packed, else = padded
) -> Tensor:
    """
    Returns: (local_experts, max_recv, C) with autograd attached
    """
```

## Two Modes

### Packed Mode (`recv_offsets=None`)
- Output: `(local_experts, sum(recv_counts), C)`
- No gaps between experts' received tokens
- Used when all experts receive same amount

### Padded Mode (`recv_offsets=[...]`)
- Output: `(local_experts, max_recv, C)`
- Each expert's data at fixed offset
- Used for variable k per expert (threshold routing)

## Memory Savings

| Copy | Before | After |
|------|--------|-------|
| 1: Gather tokens | `contiguous()` | Same (unavoidable) |
| 2: all-to-all output | Fresh allocation per expert | Pre-allocated buffer slice |
| 3: `torch.stack` | Copies all received | Eliminated |

## Backward Pass

Reverse all-to-all with swapped splits:
```python
def backward(ctx, grad_out):
    for i in range(local_experts):
        dist.all_to_all_single(
            grad_x[i],
            grad_out[i],
            output_split_sizes=input_splits[i],  # Swapped
            input_split_sizes=output_splits[i],  # Swapped
        )
```

## Usage in EP

```python
# In parallel_experts_manual.py

# Dispatch (5 calls)
tokens_received = prealloc_all_to_all(
    x_list, output_splits, input_splits, recv_offsets
)

# Expert forward
h = batched_bmm(tokens_received, W1, W2)

# Combine (similar pattern)
output = prealloc_all_to_all(
    h_list, combine_output_splits, combine_input_splits
)
```

## Design Decisions

1. **Offset-based not shape-based**: Use `recv_offsets` for flexible padding
2. **Single autograd.Function**: Attaches graph to buffer, not slices
3. **Variadic packing**: `*x_list, *output_splits, *input_splits` to support variable local_experts
4. **Backward reuses same pattern**: Just swap splits
