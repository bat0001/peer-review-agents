"""Optimized CSR-based autograd operations.

Wraps the optimized backward kernel.
"""

from __future__ import annotations

from typing import Any, Optional

import torch
from torch.amp import custom_bwd, custom_fwd

from src import kernels
from src.kernels.csr_optimized import csr_scatter_bwd_optimized_compileable

class CSRScatterOptimizedOp(torch.autograd.Function):
    """Scatter expert outputs to tokens using optimized CSR kernel.

    Forward: Standard CSR scatter (reused from src.kernels.csr).
    Backward: Optimized CSR backward with column-major loop and optional fusion.
    """

    @staticmethod
    @custom_fwd(device_type="cuda")
    def forward(
        ctx: Any,
        a_slots: torch.Tensor,
        indices_flat: torch.Tensor,
        num_tokens: int,
        max_experts: int,
        slot_indices: torch.Tensor,
        slot_offsets: torch.Tensor,
        slot_counts: torch.Tensor,
        weights: Optional[torch.Tensor] = None,
        shared_flat: Optional[torch.Tensor] = None,
        shared_weights: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            a_slots: Expert outputs (total_active, H)
            indices_flat: Flat token indices (total_active,)
            num_tokens: Total tokens
            max_experts: Max experts per token
            slot_indices: CSR indices
            slot_offsets: CSR offsets
            slot_counts: CSR counts
            weights: Optional weights (total_active,)
            shared_flat: Optional shared expert output (N, H) UNWEIGHTED.
                         If provided, output = routed + shared_flat * shared_weights.
            shared_weights: Optional weights for shared_flat (N,) = 1/normalizer.
        """
        assert a_slots.dim() == 2 and indices_flat.dim() == 1
        total_active, H = a_slots.shape
        device = a_slots.device
        dtype = a_slots.dtype

        # Initialize output
        if shared_flat is not None:
            out = shared_flat.clone()
        else:
            # We can use empty here because the kernel fully initializes the output
            # when accumulate=False (it writes 0 or accumulated value to every element)
            out = torch.empty(num_tokens, H, device=device, dtype=dtype)

        # Handle weights
        USE_WEIGHTS_VAL = 1 if weights is not None else 0
        if USE_WEIGHTS_VAL:
            w_use = weights
        else:
            w_use = a_slots # dummy

        # Save for backward
        tensors_to_save = [slot_indices, slot_offsets, slot_counts]
        if USE_WEIGHTS_VAL:
            tensors_to_save.append(weights)
            if weights.requires_grad:
                tensors_to_save.append(a_slots)
                ctx.weights_needs_grad = True
            else:
                ctx.weights_needs_grad = False
        else:
            ctx.weights_needs_grad = False
        
        ctx.has_shared_weights = shared_weights is not None
        if ctx.has_shared_weights:
            tensors_to_save.append(shared_weights)

        ctx.save_for_backward(*tensors_to_save)
        ctx.has_weights = USE_WEIGHTS_VAL == 1
        ctx.has_shared_flat = shared_flat is not None
        ctx.num_tokens = num_tokens
        ctx.max_experts = max_experts
        ctx.H = H
        ctx.total_active = total_active

        # Launch Forward Kernel (Standard)
        # We reuse the existing forward kernel via the compileable wrapper
        from src.kernels.csr import csr_scatter_sum_compileable
        
        csr_scatter_sum_compileable(
            a_slots,
            out,
            slot_indices,
            slot_offsets,
            slot_counts,
            w_use if USE_WEIGHTS_VAL else None,
            max_experts,
            use_weights=USE_WEIGHTS_VAL == 1,
            accumulate=shared_flat is not None,
            shared_expert_weights=shared_weights,
        )

        return out

    @staticmethod
    @custom_bwd(device_type="cuda")
    def backward(ctx: Any, grad_out: torch.Tensor) -> tuple:
        saved = ctx.saved_tensors
        idx = 0
        slot_indices = saved[idx]; idx += 1
        slot_offsets = saved[idx]; idx += 1
        slot_counts = saved[idx]; idx += 1

        if ctx.has_weights:
            weights = saved[idx]; idx += 1
            if ctx.weights_needs_grad:
                a_slots = saved[idx]; idx += 1
            else:
                a_slots = None
        else:
            weights = None
            a_slots = None

        if ctx.has_shared_weights:
            shared_weights = saved[idx]; idx += 1
        else:
            shared_weights = None

        N, H = grad_out.shape
        device = grad_out.device
        dtype = grad_out.dtype

        # Kernel fully writes grad_slots (each slot visited exactly once)
        grad_slots = torch.empty(ctx.total_active, H, device=device, dtype=dtype)

        if ctx.weights_needs_grad and a_slots is not None:
            # Kernel fully writes grad_weights (each slot visited exactly once)
            grad_weights = torch.empty(ctx.total_active, device=device, dtype=dtype)
        else:
            grad_weights = None

        if ctx.has_shared_flat:
            grad_shared = torch.empty(N, H, device=device, dtype=dtype) # Will be filled by kernel
        else:
            grad_shared = None

        # Launch Optimized Backward Kernel
        csr_scatter_bwd_optimized_compileable(
            grad_out,
            a_slots if a_slots is not None else grad_out,
            slot_indices,
            slot_offsets,
            slot_counts,
            weights,
            ctx.max_experts,
            grad_slots,
            grad_weights,
            add_into=ctx.has_shared_flat,
            grad_shared=grad_shared,
            shared_weights=shared_weights,
        )

        # Return gradients matching forward signature:
        # (a_slots, indices, num_tokens, max_experts, slot_indices, slot_offsets, slot_counts, weights, shared_flat, shared_weights)
        return grad_slots, None, None, None, None, None, None, grad_weights, grad_shared, None


def csr_scatter_sum_optimized(
    a_slots: torch.Tensor,
    indices_flat: torch.Tensor,
    num_tokens: int,
    max_experts: int,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
    weights: Optional[torch.Tensor] = None,
    shared_flat: Optional[torch.Tensor] = None,
    shared_weights: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    return CSRScatterOptimizedOp.apply(
        a_slots,
        indices_flat,
        num_tokens,
        max_experts,
        slot_indices,
        slot_offsets,
        slot_counts,
        weights,
        shared_flat,
        shared_weights,
    )

