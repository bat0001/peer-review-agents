"""Autograd-enabled scatter operation with optimized fused backward.

Scatter operation for converting expert-major back to token-major layout,
with optional routing weights. Features a fused backward pass that computes
both expert gradients and weight gradients in a single kernel (2× speedup).
"""

from __future__ import annotations

from typing import Any, Optional

import torch
from torch.amp import custom_bwd, custom_fwd

from src import kernels


class ScatterOp(torch.autograd.Function):
    """Scatter expert outputs to tokens with optimized backward pass.

    Forward pass: scatter with atomic accumulation (handles overlapping tokens)
    Backward pass: uses fused kernel when both gradients needed (common case)

    Key optimization:
        When both grad_expert and grad_weights are needed, a single fused
        kernel computes both outputs in one pass (~2× faster than separate
        gather + weight gradient kernels).
    """

    @staticmethod
    @custom_fwd(device_type="cuda")
    def forward(
        ctx: Any,
        expert_out: torch.Tensor,
        indices: torch.Tensor,
        num_experts: int,
        capacity: int,
        num_tokens: int,
        weights: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Scatter expert outputs to token-major order.

        Args:
            expert_out: Expert outputs (num_experts, capacity, hidden_size)
            indices: Token indices (num_experts * capacity,)
            num_experts: Number of experts
            capacity: Tokens per expert
            num_tokens: Total number of tokens
            weights: Optional routing weights (num_experts * capacity,)

        Returns:
            Token outputs (num_tokens, hidden_size)
        """
        indices = indices.contiguous()
        weights_tensor = weights.contiguous() if weights is not None else None

        out = kernels.scatter_atomic(
            expert_out,
            indices,
            num_experts=num_experts,
            capacity=capacity,
            num_tokens=num_tokens,
            weights=weights_tensor,
        )

        ctx.num_experts = num_experts
        ctx.capacity = capacity
        ctx.has_weights = weights_tensor is not None
        ctx.weights_requires_grad = bool(
            weights_tensor is not None and weights_tensor.requires_grad
        )

        # Save tensors for backward
        saved: list[torch.Tensor] = [indices]
        if weights_tensor is not None:
            saved.append(weights_tensor)
            if ctx.weights_requires_grad:
                # Need expert_out for weight gradients
                saved.append(expert_out)
        ctx.save_for_backward(*saved)

        return out

    @staticmethod
    @custom_bwd(device_type="cuda")
    def backward(ctx: Any, grad_output: torch.Tensor):
        """Compute gradients with optimized fused kernel when possible.

        Three paths:
        1. Both gradients needed (common) -> fused_gather_wgrad (2× faster)
        2. Expert gradient only -> gather
        3. Weight gradient only -> raise error (unsupported rare case)

        Returns:
            Tuple of gradients: (grad_expert, None, None, None, None, grad_weights)
        """
        grad_output = grad_output.contiguous()

        # Unpack saved tensors
        saved = ctx.saved_tensors
        offset = 0
        indices = saved[offset]
        offset += 1

        weights = None
        expert_cached = None
        if ctx.has_weights:
            weights = saved[offset]
            offset += 1
            if ctx.weights_requires_grad:
                expert_cached = saved[offset]

        grad_expert = None
        grad_weights = None

        # Path 1: FUSED - both gradients needed (common case, ~2× speedup)
        if ctx.needs_input_grad[0] and ctx.weights_requires_grad and expert_cached is not None:
            grad_expert, grad_weights = kernels.fused_gather_wgrad(
                grad_output,
                expert_cached,
                indices,
                num_experts=ctx.num_experts,
                capacity=ctx.capacity,
                weights=weights,
            )
            grad_weights = grad_weights.to(weights.dtype)

        # Path 2: Only expert gradient needed
        elif ctx.needs_input_grad[0]:
            grad_expert = kernels.gather(
                grad_output,
                indices,
                num_experts=ctx.num_experts,
                capacity=ctx.capacity,
                weights=weights,
            )

        # Path 3: Only weight gradient needed (rare, unsupported)
        elif ctx.weights_requires_grad:
            raise RuntimeError(
                "Scatter backward: Cannot compute weight gradients without expert gradients. "
                "This is an unsupported edge case. If you need this functionality, "
                "please ensure expert_out.requires_grad=True or file an issue."
            )

        return grad_expert, None, None, None, None, grad_weights


scatter = ScatterOp.apply


__all__ = ['scatter', 'ScatterOp']