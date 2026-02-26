"""Autograd-enabled gather operation.

Simple gather operation for converting token-major to expert-major layout.
Does not apply weights in forward pass (weights are applied in scatter).
"""

from __future__ import annotations

from typing import Any

import torch
from torch.amp import custom_bwd, custom_fwd

from src import kernels


class GatherOp(torch.autograd.Function):
    """Gather tokens into expert-major order with autograd support.

    Forward pass: gather tokens without weights
    Backward pass: scatter gradients without weights

    This is used for simple token permutation where routing weights
    are applied later (e.g., in the scatter operation).
    """

    @staticmethod
    @custom_fwd(device_type="cuda")
    def forward(
        ctx: Any,
        x: torch.Tensor,
        indices: torch.Tensor,
        num_experts: int,
        capacity: int,
    ) -> torch.Tensor:
        """Gather tokens into expert-major order.

        Args:
            x: Input tokens (num_tokens, hidden_size)
            indices: Token indices (num_experts * capacity,)
            num_experts: Number of experts
            capacity: Tokens per expert

        Returns:
            Expert-major buffer (num_experts, capacity, hidden_size)
        """
        ctx.save_for_backward(indices)
        ctx.num_experts = num_experts
        ctx.capacity = capacity
        ctx.num_tokens = x.shape[0]

        return kernels.gather(
            x,
            indices,
            num_experts=num_experts,
            capacity=capacity,
            weights=None,
        )

    @staticmethod
    @custom_bwd(device_type="cuda")
    def backward(ctx: Any, grad_output: torch.Tensor):
        """Scatter gradients back to token-major order.

        Args:
            grad_output: Gradient w.r.t. expert-major output

        Returns:
            grad_x: Gradient w.r.t. token-major input
        """
        grad_output = grad_output.contiguous()
        (indices,) = ctx.saved_tensors

        grad_x = kernels.scatter_atomic(
            grad_output,
            indices,
            num_experts=ctx.num_experts,
            capacity=ctx.capacity,
            num_tokens=ctx.num_tokens,
            weights=None,
        )

        return grad_x, None, None, None


def gather(
    x: torch.Tensor,
    indices: torch.Tensor,
    *,
    num_experts: int,
    capacity: int,
) -> torch.Tensor:
    """Gather tokens into expert-major order.

    Keyword-only wrapper around GatherOp for cleaner API.

    Args:
        x: Input tokens (num_tokens, hidden_size)
        indices: Token indices (num_experts * capacity,)
        num_experts: Number of experts
        capacity: Tokens per expert

    Returns:
        Expert-major buffer (num_experts, capacity, hidden_size)
    """
    return GatherOp.apply(x, indices, num_experts, capacity)


__all__ = ['gather', 'GatherOp']