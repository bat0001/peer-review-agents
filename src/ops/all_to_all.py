"""
All-to-all operation autograd wrapper for Expert Parallelism.

Used as the communication primitive in both EP phases:
- Dispatch: forward pass sends tokens to expert-owning ranks
- Combine: reverse pass sends expert outputs back to original ranks

Implementation adapted from Databricks/MegaBlocks: https://github.com/databricks/megablocks/blob/main/megablocks/layers/all_to_all.py

world_size: 8
B_local: local batch size (usually 16k on A5000)
expansion: 8
granularity: 2
Capacity: tokens per expert = B_local * world_size / (E) (e.g., 16k * 8 / 8 = 16k)
C: hidden size (512 or 1024)
total_sent_tokens: may change due to routing, asymptotically (B_local * E / world_size = 16k * 8 / 8 = 16k)
output_split_sizes: e.g. [3k, 2k, 3k, 5k, ..., 4k] # sum to B_local * E / world_size * G = 16k * 8 / 8 * 2 = 32k
input_split_sizes: e.g. [4k, 5k, 4k, 3k, ..., 2k] # sum to an uncertain number as routing changes, but usually around 32k
"""

import torch
import torch.distributed as dist

from typing import Optional, List, Tuple

class AllToAllOp(torch.autograd.Function):

    @staticmethod
    def forward(
        ctx,
        x: torch.Tensor,  # input tensor, shape: (B_local, C)
        output_split_sizes: List[int],
        input_split_sizes: List[int],
        out = None,
        group=None,  # process group
        async_op=False,
    ):
        if out is None:
            out = torch.empty((sum(output_split_sizes),) + x.shape[1:], device=x.device, dtype=x.dtype)
        else:
            assert out.shape == (sum(output_split_sizes),) + x.shape[1:], "Output tensor shape mismatch"

        ctx.input_shape = x.shape
        ctx.output_split_sizes = output_split_sizes
        ctx.input_split_sizes = input_split_sizes
        ctx.group = group
        handle = dist.all_to_all_single(
            out,
            x,
            output_split_sizes=output_split_sizes,
            input_split_sizes=input_split_sizes,
            group=group,
            async_op=async_op,
        )
        # Always return (out, handle) for autograd to work
        return out, handle

    @staticmethod
    def backward(ctx, grad, _):
        """ _ omits the grad of handle, which is not differentiable"""
        if ctx.needs_input_grad[0]:
            out = torch.empty(ctx.input_shape, device=grad.device, dtype=grad.dtype)
            dist.all_to_all_single(
                out,
                grad,
                output_split_sizes=ctx.input_split_sizes,
                input_split_sizes=ctx.output_split_sizes,
                group=ctx.group,
            )
            # Return grads for: x, output_split_sizes, input_split_sizes, out, group, async_op
            return out, None, None, None, None, None
        return None, None, None, None, None, None


def all_to_all(
    x: torch.Tensor,
    output_split_sizes: List[int],
    input_split_sizes: List[int],
    out: Optional[torch.Tensor] = None,
    group: Optional[dist.ProcessGroup] = None,
    async_op: bool = False
) -> Tuple[torch.Tensor, Optional[dist.Work]]:
    """
    All-to-all operation.
    """
    return AllToAllOp.apply(x, output_split_sizes, input_split_sizes, out, group, async_op)
