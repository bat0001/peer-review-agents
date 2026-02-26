# Plan: Zero-Copy All-to-All in Expert Parallelism

## Problem

In `src/models/engines/parallel_experts_manual.py`, the per-expert all-to-all loop has unnecessary memory copies:

```python
# Current implementation (lines 176-210, 224-232)
for i in range(self.local_experts):
    tokens_to_send = x_flat[send_indices % n_tokens].contiguous()  # Copy 1 - UNAVOIDABLE
    received, _ = all_to_all(tokens_to_send, ...)                  # Copy 2 - allocates new buffer
    received_tokens_list.append(received)

tokens_received = torch.stack(received_tokens_list)                # Copy 3 - stacks into new tensor
```

## Solution: Custom PreallocAllToAll Autograd Function

The naive approach of passing `out=buffer[i]` doesn't work because autograd graph attaches to the returned tensor, not the pre-allocated buffer. We need a custom autograd function that:
1. Takes the entire pre-allocated buffer
2. Writes all experts' data into it via NCCL
3. Returns the buffer WITH autograd graph attached

### New Autograd Function

Add to `src/ops/all_to_all.py`:

```python
class PreallocAllToAllOp(torch.autograd.Function):
    """
    Batched all-to-all for multiple experts with pre-allocated output buffer.

    Eliminates per-expert allocation and final torch.stack by:
    1. Pre-allocating output buffer: (local_experts, k_global, C)
    2. Writing each expert's received tokens directly into buffer[i]
    3. Returning the buffer with autograd graph attached
    """

    @staticmethod
    def forward(
        ctx,
        out: torch.Tensor,                    # Pre-allocated: (local_experts, k_global, C)
        *inputs_and_metadata,                 # Flattened: [x0, x1, ..., splits0, splits1, ...]
    ):
        """
        Args:
            out: Pre-allocated output buffer (local_experts, k_global, C)
            inputs_and_metadata: Variadic args containing:
                - x_i: Input tensors to send for expert i
                - output_splits_i: List[int] for expert i
                - input_splits_i: List[int] for expert i

        The metadata is packed as:
            x_0, x_1, ..., x_{n-1},
            output_splits_0, output_splits_1, ..., output_splits_{n-1},
            input_splits_0, input_splits_1, ..., input_splits_{n-1}
        """
        local_experts = out.shape[0]

        # Unpack variadic args
        x_list = inputs_and_metadata[:local_experts]
        output_splits_list = inputs_and_metadata[local_experts:2*local_experts]
        input_splits_list = inputs_and_metadata[2*local_experts:3*local_experts]

        # Save for backward
        ctx.local_experts = local_experts
        ctx.input_shapes = [x.shape for x in x_list]
        ctx.output_splits_list = output_splits_list
        ctx.input_splits_list = input_splits_list

        # Execute all-to-all for each expert into pre-allocated slices
        for i in range(local_experts):
            dist.all_to_all_single(
                out[i],           # Write directly into buffer slice
                x_list[i],
                output_split_sizes=list(output_splits_list[i]),
                input_split_sizes=list(input_splits_list[i]),
            )

        return out  # Return buffer with autograd attached

    @staticmethod
    def backward(ctx, grad_out):
        """
        Backward: reverse all-to-all for each expert.

        grad_out: (local_experts, k_global, C) - gradient w.r.t. output buffer
        Returns: (None for out, grad_x_0, grad_x_1, ..., None for splits...)
        """
        local_experts = ctx.local_experts
        input_shapes = ctx.input_shapes
        output_splits_list = ctx.output_splits_list
        input_splits_list = ctx.input_splits_list

        # Compute gradient for each input
        grad_inputs = []
        for i in range(local_experts):
            grad_x = torch.empty(input_shapes[i], device=grad_out.device, dtype=grad_out.dtype)

            # Reverse all-to-all: swap input/output splits
            dist.all_to_all_single(
                grad_x,
                grad_out[i],
                output_split_sizes=list(input_splits_list[i]),   # Swapped
                input_split_sizes=list(output_splits_list[i]),   # Swapped
            )
            grad_inputs.append(grad_x)

        # Return: (grad_out=None, grad_x_0, grad_x_1, ..., None for all splits)
        # None for 'out' parameter, then grads for x_list, then None for splits
        return (None,) + tuple(grad_inputs) + (None,) * (2 * local_experts)


def prealloc_all_to_all(
    x_list: List[torch.Tensor],
    output_splits_list: List[List[int]],
    input_splits_list: List[List[int]],
    out: torch.Tensor,
) -> torch.Tensor:
    """
    Batched all-to-all with pre-allocated output buffer.

    Args:
        x_list: List of input tensors, one per local expert
        output_splits_list: List of output split sizes per expert
        input_splits_list: List of input split sizes per expert
        out: Pre-allocated output buffer (local_experts, k_global, C)

    Returns:
        out: Same buffer, now filled with received data and with autograd attached
    """
    # Pack into variadic args for autograd.Function
    return PreallocAllToAllOp.apply(
        out,
        *x_list,
        *output_splits_list,
        *input_splits_list,
    )
```

### Usage in parallel_experts_manual.py

```python
def forward_topk(self, x, ...):
    # ... routing logic, compute indices and splits ...

    # Collect tokens for dispatch (still need this copy)
    x_list = []
    for i in range(self.local_experts):
        send_indices = ...  # compute as before
        x_list.append(x_flat[send_indices % n_tokens].contiguous())

    # Pre-allocate output buffer
    tokens_received = torch.empty(
        (self.local_experts, k_global, C),
        device=x.device, dtype=x.dtype
    )

    # Single call - no loop, no stack, autograd works!
    tokens_received = prealloc_all_to_all(
        x_list,
        output_splits_sizes,  # List[List[int]]
        input_splits_sizes,   # List[List[int]]
        out=tokens_received,
    )

    # Expert forward
    h = self._batched_expert_forward(tokens_received)

    # Similar pattern for combine all-to-all...
```

## Files to Modify

1. `src/ops/all_to_all.py` - Add `PreallocAllToAllOp` class and `prealloc_all_to_all` function
2. `src/models/engines/parallel_experts_manual.py` - Use new function in `forward_topk`

## Summary

| Copy | Current | After |
|------|---------|-------|
| 1: Gather tokens | `x_flat[indices].contiguous()` | Same (unavoidable) |
| 2: all_to_all output | Fresh allocation per expert | Pre-allocated buffer slice |
| 3: torch.stack | Copies all received | Eliminated |

**Key insight**: By wrapping the entire batched operation in one autograd.Function, we attach the autograd graph to the pre-allocated buffer itself, not to individual slices.
