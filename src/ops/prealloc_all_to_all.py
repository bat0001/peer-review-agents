"""
Pre-allocated All-to-All for Expert Parallelism.

Unified API for dispatch and combine with optional padding support.
- recv_offsets=None: Packed mode (allocate with empty)
- recv_offsets=[0, max_k, ...]: Padded mode (allocate with zeros for gaps)
"""

import torch
import torch.distributed as dist
from typing import List, Optional


class PreallocAllToAllOp(torch.autograd.Function):
    """
    Batched all-to-all with internal buffer allocation.

    Eliminates per-expert allocation and torch.stack/cat overhead.
    """

    @staticmethod
    def forward(
        ctx,
        recv_offsets: Optional[List[int]],
        total_size: int,
        hidden_size: int,
        device: torch.device,
        dtype: torch.dtype,
        *inputs_and_metadata,
    ):
        n_experts = len(inputs_and_metadata) // 3
        x_list = inputs_and_metadata[:n_experts]
        output_splits_list = inputs_and_metadata[n_experts:2*n_experts]
        input_splits_list = inputs_and_metadata[2*n_experts:]

        # Asserts
        assert len(x_list) == n_experts, f"Expected {n_experts} inputs, got {len(x_list)}"
        assert len(output_splits_list) == n_experts
        assert len(input_splits_list) == n_experts
        for i, x in enumerate(x_list):
            expected_send = sum(input_splits_list[i])
            assert x.shape[0] == expected_send, \
                f"Expert {i}: input size {x.shape[0]} != sum(input_splits) {expected_send}"
            assert x.shape[1] == hidden_size, \
                f"Expert {i}: hidden {x.shape[1]} != expected {hidden_size}"

        # Compute offsets if not provided (packed mode)
        if recv_offsets is None:
            recv_offsets = []
            offset = 0
            for i in range(n_experts):
                recv_offsets.append(offset)
                offset += sum(output_splits_list[i])
            # Packed: use empty (no gaps)
            out = torch.empty((total_size, hidden_size), device=device, dtype=dtype)
        else:
            # Padded: use zeros (gaps need to be zero)
            assert len(recv_offsets) == n_experts
            out = torch.zeros((total_size, hidden_size), device=device, dtype=dtype)

        # Save for backward
        ctx.n_experts = n_experts
        ctx.input_shapes = [x.shape for x in x_list]
        ctx.output_splits_list = output_splits_list
        ctx.input_splits_list = input_splits_list
        ctx.recv_offsets = recv_offsets

        # Execute all-to-all for each expert at specified offsets
        for i in range(n_experts):
            recv_size = sum(output_splits_list[i])
            dist.all_to_all_single(
                out[recv_offsets[i]:recv_offsets[i]+recv_size],
                x_list[i],
                output_split_sizes=list(output_splits_list[i]),
                input_split_sizes=list(input_splits_list[i]),
            )

        return out

    @staticmethod
    def backward(ctx, grad_out):
        """
        Backward: reverse all-to-all, slicing at same offsets.

        No zero-grad handling needed because:
        - Dispatch backward: we slice at offsets, ignoring padding
        - Combine backward: inputs were correctly sized (sliced before passing)
        """
        n_experts = ctx.n_experts
        recv_offsets = ctx.recv_offsets
        output_splits_list = ctx.output_splits_list
        input_splits_list = ctx.input_splits_list
        input_shapes = ctx.input_shapes

        # Ensure grad_out is contiguous (may be expanded from sum())
        grad_out = grad_out.contiguous()

        grad_inputs = []
        for i in range(n_experts):
            recv_size = sum(output_splits_list[i])
            grad_x = torch.empty(input_shapes[i], device=grad_out.device, dtype=grad_out.dtype)

            # Slice at same offsets, ignore padding
            dist.all_to_all_single(
                grad_x,
                grad_out[recv_offsets[i]:recv_offsets[i]+recv_size],
                output_split_sizes=list(input_splits_list[i]),
                input_split_sizes=list(output_splits_list[i]),
            )
            grad_inputs.append(grad_x)

        # Return: None for (recv_offsets, total_size, hidden_size, device, dtype),
        # then grads for x_list, then None for splits
        return (None, None, None, None, None) + tuple(grad_inputs) + (None,) * (2 * n_experts)


def prealloc_all_to_all(
    x_list: List[torch.Tensor],
    output_splits_list: List[List[int]],
    input_splits_list: List[List[int]],
    hidden_size: int,
    device: torch.device,
    dtype: torch.dtype,
    recv_offsets: Optional[List[int]] = None,
) -> torch.Tensor:
    """
    Batched all-to-all with internal buffer allocation.

    Args:
        x_list: List of input tensors, one per local expert
        output_splits_list: Tokens received from each rank, per expert
        input_splits_list: Tokens sent to each rank, per expert
        hidden_size: Hidden dimension C
        device: Target device
        dtype: Target dtype
        recv_offsets: Where to write each expert's data. None = packed (no gaps).
                      For padded mode, offsets should be uniformly spaced (stride = k_actual_max).

    Returns:
        out: Buffer filled with received data, shape (total_size, hidden_size)
    """
    n_experts = len(x_list)
    assert n_experts > 0, "x_list cannot be empty"
    assert len(output_splits_list) == n_experts
    assert len(input_splits_list) == n_experts

    # Compute total size
    if recv_offsets is None:
        # Packed mode: sum of actual receives
        total_size = sum(sum(splits) for splits in output_splits_list)
    else:
        # Padded mode: infer stride from recv_offsets to get correct padded size
        # recv_offsets = [0, stride, 2*stride, ...] where stride = k_actual_max
        assert len(recv_offsets) == n_experts
        if n_experts >= 2:
            stride = recv_offsets[1] - recv_offsets[0]
            total_size = recv_offsets[-1] + stride
        else:
            # Single expert: no padding needed
            total_size = sum(output_splits_list[0])

    return PreallocAllToAllOp.apply(
        recv_offsets,
        total_size,
        hidden_size,
        device,
        dtype,
        *x_list,
        *output_splits_list,
        *input_splits_list,
    )
