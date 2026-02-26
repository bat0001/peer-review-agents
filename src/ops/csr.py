"""CSR-based autograd operations for token-parallel scatter.

Provides autograd-enabled gather and scatter operations using CSR (Compressed
Sparse Row) format for efficient token-parallel processing. The key difference
from the standard ops is:

- Standard ops: slot-level parallelism (one program per expert-token pair)
- CSR ops: token-level parallelism (one program per token, summing contributions)

This can be more efficient when tokens have multiple contributing experts and
the scatter operation can be parallelized across tokens rather than slots.
"""

from __future__ import annotations

from typing import Any, Optional

import torch
from torch.amp import custom_bwd, custom_fwd

from src import kernels


class CSRGatherOp(torch.autograd.Function):
    """Gather tokens into expert-major order with CSR-based backward.

    Forward pass: y[e, s, :] = x[indices[e, s], :] (zeros if indices == -1)
    Backward pass: grad_x = scatter-reduce(sum) of grad_y using CSR kernel

    This is the inverse operation of CSRScatterOp. The forward pass is a simple
    gather (no CSR needed), but the backward uses the CSR scatter kernel to
    accumulate gradients back to tokens.
    """

    @staticmethod
    @custom_fwd(device_type="cuda")
    def forward(
        ctx: Any,
        x_tokens: torch.Tensor,
        indices: torch.Tensor,
        max_experts: int,
        slot_indices: torch.Tensor,
        slot_offsets: torch.Tensor,
        slot_counts: torch.Tensor,
    ) -> torch.Tensor:
        """Gather tokens into expert-major layout.

        Args:
            x_tokens: Input tokens (N, H)
            indices: Expert-major indices (E, C) with token ids or -1
            max_experts: Maximum contributors per token (for CSR builder)

        Returns:
            Expert-major buffer (E, C, H)
        """
        assert x_tokens.dim() == 2 and indices.dim() == 2
        N, H = x_tokens.shape
        E, C = indices.shape
        device = x_tokens.device
        dtype = x_tokens.dtype

        # Simple gather: y[e, s, :] = x[indices[e, s], :]
        flat = indices.reshape(-1)  # (E*C,)
        mask = flat >= 0
        y_flat = torch.zeros(E * C, H, device=device, dtype=dtype)
        if mask.any():
            y_flat[mask] = x_tokens[flat[mask]]
        y = y_flat.view(E, C, H)

        # Save for backward
        # Save CSR data for backward
        ctx.save_for_backward(slot_indices, slot_offsets, slot_counts)
        ctx.N = N
        ctx.H = H
        ctx.max_experts = max_experts

        return y

    @staticmethod
    @custom_bwd(device_type="cuda")
    def backward(ctx: Any, grad_y: torch.Tensor) -> tuple:
        """Scatter gradients back to tokens using CSR kernel.

        Args:
            grad_y: Gradient w.r.t. expert-major output (E, C, H)

        Returns:
            Tuple of gradients: (grad_x, None, None)
        """
        slot_idx, slot_offs, counts = ctx.saved_tensors
        E, C, H = grad_y.shape
        assert H == ctx.H
        device = grad_y.device
        dtype = grad_y.dtype

        # Flatten grad_y to (E*C, H)
        grad_y2d = grad_y.reshape(E * C, H).contiguous()
        
        # Kernel with ACCUMULATE=0 fully initializes the output
        grad_x = torch.empty(ctx.N, H, device=device, dtype=dtype)

        # Use CSR scatter kernel to accumulate gradients
        grid = (ctx.N,)
        kernels._csr_scatter_sum[grid](
            grad_y2d, grad_x,
            slot_idx, slot_offs, counts, grad_x,  # grad_x as dummy weights pointer (not used when USE_WEIGHTS=0)
            MAX_EXPERTS=ctx.max_experts,
            NUM_COLUMNS=H,
            USE_WEIGHTS=0,
            ACCUMULATE=0,
            SHARED_EXPERT_WEIGHTS=0,
            shared_expert_weights=grad_x,  # dummy pointer (not used when SHARED_EXPERT_WEIGHTS=0)
        )

        return grad_x, None, None, None, None, None  # only x_tokens has grad


class CSRScatterOp(torch.autograd.Function):
    """Scatter expert outputs to tokens using CSR kernel with autograd.

    Forward pass: out_tokens = sum_{slots->token} (w[l] * expert_slots[l, :])
    Backward pass: gather gradients to slots + compute weight gradients

    This is the key operation that provides correct gradients through the
    router weights. The backward pass computes:
    - grad_expert[l, :] = w[l] * grad_out[token_of_l, :]
    - grad_w[l] = dot(expert[l, :], grad_out[token_of_l, :])

    When add_into=True with add_into_buffer:
    - Forward accumulates into the provided buffer instead of zeros
    - Backward also returns grad_shared (gradient for the original buffer content)
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
        """Scatter expert outputs to tokens using CSR kernel with fused weighting.

        Applies all weights in one fused pass:
        - Routed: output[idx] += a_slots[slot] * weights[slot]
        - Shared: output[idx] += shared_flat[idx] * shared_weights[idx]

        Args:
            a_slots: Expert outputs (total_active, H) - flattened, UNWEIGHTED
            indices_flat: Flat token indices (total_active,)
            num_tokens: Total number of tokens (N)
            max_experts: Maximum contributors per token
            slot_indices: CSR slot indices
            slot_offsets: CSR offsets
            slot_counts: CSR counts
            weights: Per-slot weights (total_active,) for routed experts
            shared_flat: Optional shared expert output (N, H) UNWEIGHTED
            shared_weights: Optional shared expert weights (N,) = 1/normalizer

        Returns:
            Token outputs (N, H)
        """
        assert a_slots.dim() == 2 and indices_flat.dim() == 1
        total_active, H = a_slots.shape
        assert indices_flat.shape[0] == total_active, \
            f"indices_flat must have same length as a_slots, got {indices_flat.shape[0]} vs {total_active}"
        device = a_slots.device
        dtype = a_slots.dtype

        # Determine if we have shared expert
        has_shared = shared_flat is not None and shared_weights is not None
        if has_shared:
            assert shared_flat.shape == (num_tokens, H), \
                f"shared_flat must be (N, H)={(num_tokens, H)}, got {shared_flat.shape}"
            assert shared_weights.shape == (num_tokens,), \
                f"shared_weights must be (N,)=({num_tokens},), got {shared_weights.shape}"

        # Initialize output buffer with UNWEIGHTED shared expert (if provided)
        # The kernel will apply shared_weights during accumulation (fused)
        # NOTE: Must clone because we save shared_flat for backward, and kernel mutates out
        if has_shared:
            out = shared_flat.clone()
        else:
            # We can use empty here because the kernel fully initializes the output
            # when accumulate=False (it writes 0 or accumulated value to every element)
            out = torch.empty(num_tokens, H, device=device, dtype=dtype)

        # Set up weights for routed experts
        USE_WEIGHTS_VAL = 1 if weights is not None else 0
        if USE_WEIGHTS_VAL:
            assert weights.shape == (total_active,), f"weights must be (total_active,), got {weights.shape}"
            w_use = weights
        else:
            # Kernel ignores weights when USE_WEIGHTS=0 but still expects a pointer.
            w_use = a_slots

        # Save for backward
        # We need CSR arrays for token-parallel backward pass
        # We need weights for grad_a even if weights doesn't require grad
        # We need a_slots only if weights requires grad (for grad_w)
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

        # Save shared tensors for backward if provided
        if has_shared:
            # tensors_to_save.append(shared_flat) # Not needed if we don't compute grad_shared_weights
            tensors_to_save.append(shared_weights)

        ctx.save_for_backward(*tensors_to_save)

        ctx.has_weights = USE_WEIGHTS_VAL == 1
        ctx.has_shared = has_shared
        ctx.num_tokens = num_tokens
        ctx.max_experts = max_experts
        ctx.H = H
        ctx.total_active = total_active

        # Launch CSR scatter kernel for routed experts
        # Kernel applies shared_weights to the buffer content during accumulation (fused)
        kernels.csr_scatter_sum_compileable(
            a_slots,
            out,
            slot_indices,
            slot_offsets,
            slot_counts,
            w_use if USE_WEIGHTS_VAL else None,
            max_experts,
            use_weights=USE_WEIGHTS_VAL == 1,
            accumulate=has_shared,
            shared_expert_weights=shared_weights,
        )

        return out

    @staticmethod
    @custom_bwd(device_type="cuda")
    def backward(ctx: Any, grad_out: torch.Tensor) -> tuple:
        """Compute gradients: gather to slots + weight gradients using CSR kernel.

        For shared expert (output = shared_flat * shared_weights):
        - grad_shared_flat = grad_out * shared_weights
        - grad_shared_weights = (grad_out * shared_flat).sum(dim=-1)

        Args:
            grad_out: Gradient w.r.t. token outputs (N, H)

        Returns:
            Tuple of gradients for all forward args:
            (grad_a, None, None, None, None, None, None, grad_w, grad_shared_flat, grad_shared_weights)
        """
        saved = ctx.saved_tensors

        # Unpack saved tensors based on what we saved
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

        if ctx.has_shared:
            # shared_flat = saved[idx]; idx += 1
            shared_weights = saved[idx]; idx += 1
            shared_flat = None 
        else:
            shared_flat = None
            shared_weights = None

        N, H = grad_out.shape
        total_active = ctx.total_active
        device = grad_out.device
        dtype = grad_out.dtype

        # Allocate output gradients
        # grad_a is always computed (gradient w.r.t expert slots)
        # Kernel fully writes grad_slots (each slot visited exactly once)
        grad_slots = torch.empty(total_active, H, device=device, dtype=dtype)

        # grad_w is computed only if needed
        if ctx.weights_needs_grad and a_slots is not None:
            # Kernel fully writes grad_weights (each slot visited exactly once)
            grad_weights = torch.empty(total_active, device=device, dtype=dtype)
        else:
            grad_weights = None

        if ctx.has_shared:
            grad_shared_flat = torch.empty(N, H, device=device, dtype=dtype)
        else:
            grad_shared_flat = None

        # Launch CSR backward kernel (token-parallel) for routed experts
        kernels.csr_scatter_bwd_compileable(
            grad_out,
            a_slots if a_slots is not None else grad_out,  # dummy if not needed
            slot_indices,
            slot_offsets,
            slot_counts,
            weights,
            ctx.max_experts,
            grad_slots,
            grad_weights,
            add_into=ctx.has_shared,
            grad_shared=grad_shared_flat,
            shared_weights=shared_weights,
        )

        # Compute gradients for shared expert if applicable
        # output = shared_flat * shared_weights.unsqueeze(-1)
        # grad_shared_flat = grad_out * shared_weights.unsqueeze(-1)
        # grad_shared_weights = (grad_out * shared_flat).sum(dim=-1)
        if ctx.has_shared:
            # grad_shared_flat = grad_out * shared_weights.unsqueeze(-1)
            # grad_shared_weights = (grad_out * shared_flat).sum(dim=-1)
            grad_shared_weights = None
        else:
            grad_shared_flat = None
            grad_shared_weights = None

        # Return gradients for all forward args:
        # (a_slots, indices, num_tokens, max_experts, slot_indices, slot_offsets, slot_counts, weights, shared_flat, shared_weights)
        return grad_slots, None, None, None, None, None, None, grad_weights, grad_shared_flat, grad_shared_weights


def csr_gather(
    x_tokens: torch.Tensor,
    indices: torch.Tensor,
    max_experts: int,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
) -> torch.Tensor:
    """Gather tokens into expert-major order.

    Convenience wrapper around CSRGatherOp.

    Args:
        x_tokens: Input tokens (N, H)
        indices: Expert-major indices (E, C)
        max_experts: Maximum contributors per token
        slot_indices: Precomputed CSR slot indices (E*C,)
        slot_offsets: CSR offsets (N,)
        slot_counts: CSR counts (N,)

    Returns:
        Expert-major buffer (E, C, H)
    """
    return CSRGatherOp.apply(
        x_tokens,
        indices,
        max_experts,
        slot_indices,
        slot_offsets,
        slot_counts,
    )


def csr_scatter_sum(
    a_slots: torch.Tensor,
    indices_flat: torch.Tensor,
    num_tokens: int,
    max_experts: int,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
    weights_flat: Optional[torch.Tensor] = None,
    shared_flat: Optional[torch.Tensor] = None,
    shared_weights: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    """Scatter expert outputs to tokens using CSR kernel with fused weighting.

    Convenience wrapper around CSRScatterOp.

    The kernel applies all weights in one fused pass:
    - Routed: output[idx] += a_slots[slot] * weights_flat[slot]
    - Shared: output[idx] += shared_flat[idx] * shared_weights[idx]

    Args:
        a_slots: Expert outputs (total_active, H) - flattened, UNWEIGHTED
        indices_flat: Flat token indices (total_active,)
        num_tokens: Total number of tokens (N)
        max_experts: Maximum contributors per token
        slot_indices: Precomputed CSR slot indices (total_active,)
        slot_offsets: CSR offsets (N,)
        slot_counts: CSR counts (N,)
        weights_flat: Per-slot weights (total_active,) for routed experts
        shared_flat: Optional shared expert output (N, H) UNWEIGHTED
        shared_weights: Optional shared expert weights (N,) = 1/normalizer

    Returns:
        Token outputs (N, H)
    """
    return CSRScatterOp.apply(
        a_slots,
        indices_flat,
        num_tokens,
        max_experts,
        slot_indices,
        slot_offsets,
        slot_counts,
        weights_flat,
        shared_flat,
        shared_weights,
    )


__all__ = ['csr_gather', 'csr_scatter_sum', 'CSRGatherOp', 'CSRScatterOp']
