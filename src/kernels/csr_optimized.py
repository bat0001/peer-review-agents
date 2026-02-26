"""Optimized CSR scatter backward kernel.

Optimizations:
1. Load entire grad_out row at once (fits in registers for typical hidden dims).
2. Reuse grad_out across all experts for this token.
3. Fused grad_shared update (add_into support).
"""

from __future__ import annotations

from typing import Optional

import torch
import torch.library
import triton
import triton.language as tl

# Import build_slot_indices to avoid duplication
from src.kernels.csr import build_slot_indices

# Re-export build_slot_indices
__all__ = ['build_slot_indices', '_csr_scatter_bwd_optimized', 'csr_scatter_bwd_optimized_compileable']


@triton.autotune(
    configs=[
        triton.Config({}, num_warps=2),
        triton.Config({}, num_warps=4),
        triton.Config({}, num_warps=8),
    ],
    key=['NUM_COLUMNS', 'MAX_EXPERTS'],
)
@triton.jit
def _csr_scatter_bwd_optimized(
    grad_out_ptr,       # Input: (N, H)
    input_slots_ptr,    # Input: (E*C, H) - Needed for grad_w dot product
    weights_ptr,        # Input: (E*C,)
    slot_indices_ptr,   # Input: CSR indices (E*C,)
    slot_offsets_ptr,   # Input: CSR offsets (N,)
    slot_counts_ptr,    # Input: CSR counts (N,)
    grad_slots_ptr,     # Output: (E*C, H)
    grad_weights_ptr,   # Output: (E*C,)
    grad_shared_ptr,    # Output: (N, H) - gradient for shared expert (only when ADD_INTO=1)
    shared_weights_ptr, # Input: (N,) - shared expert weights

    MAX_EXPERTS: tl.constexpr,
    NUM_COLUMNS: tl.constexpr,
    USE_WEIGHTS: tl.constexpr,
    NEED_GRAD_W: tl.constexpr,
    ADD_INTO: tl.constexpr,  # whether we used add_into in the forward pass
    SHARED_WEIGHTS: tl.constexpr, # whether we used shared weights
):
    """
    Backward: Gather gradients from tokens to slots.
    Parallelism: Token-Parallel (one program per token).

    Strategy:
    - Launch 1 program per token.
    - Load entire grad_out row at once (no column blocking).
    - Reuse grad_out across all contributing experts.
    """
    pid = tl.program_id(0)

    # 1. CSR Setup
    start = tl.load(slot_offsets_ptr + pid)
    count = tl.load(slot_counts_ptr + pid)

    # 2. Load entire grad_out row at once
    grad_out_row = grad_out_ptr + pid * NUM_COLUMNS
    offsets = tl.arange(0, NUM_COLUMNS)
    g = tl.load(grad_out_row + offsets).to(tl.float32)

    # 3. Loop over Experts
    for i in range(MAX_EXPERTS):
        if i < count:
            slot_idx = tl.load(slot_indices_ptr + start + i)

            # Load weight
            w_val = 1.0
            if USE_WEIGHTS:
                w_val = tl.load(weights_ptr + slot_idx).to(tl.float32)

            # Pointers for this slot
            grad_slots_row = grad_slots_ptr + slot_idx * NUM_COLUMNS

            # --- Compute grad_x = grad_out * weight ---
            d_slot = g * w_val
            tl.store(grad_slots_row + offsets, d_slot.to(grad_slots_ptr.dtype.element_ty))

            # --- Compute grad_w = dot(grad_out, input_slot) ---
            if NEED_GRAD_W:
                input_slots_row = input_slots_ptr + slot_idx * NUM_COLUMNS
                x = tl.load(input_slots_row + offsets).to(tl.float32)
                dot_val = tl.sum(g * x)
                tl.store(grad_weights_ptr + slot_idx, dot_val.to(grad_weights_ptr.dtype.element_ty))

    # 4. Compute grad_shared = grad_out * shared_weights (identity if no weights)
    if ADD_INTO:
        grad_shared_row = grad_shared_ptr + pid * NUM_COLUMNS
        
        sw_val = 1.0
        if SHARED_WEIGHTS:
            sw_val = tl.load(shared_weights_ptr + pid).to(tl.float32)
        
        d_shared = g * sw_val
        tl.store(grad_shared_row + offsets, d_shared.to(grad_shared_ptr.dtype.element_ty))


@torch.library.custom_op("nanogec::csr_scatter_bwd_optimized", mutates_args={"grad_slots", "grad_weights"})
def csr_scatter_bwd_optimized_compileable(
    grad_out: torch.Tensor,
    input_slots: torch.Tensor,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
    weights: Optional[torch.Tensor],
    max_experts: int,
    grad_slots: torch.Tensor,
    grad_weights: Optional[torch.Tensor],
    add_into: bool = False,
    grad_shared: Optional[torch.Tensor] = None,
    shared_weights: Optional[torch.Tensor] = None,
) -> None:
    """CSR-based backward pass wrapper for token-parallel gradient computation (Optimized).

    Token-parallel strategy: One program per token.
    Optimized to reuse grad_out and support add_into fusion.

    Args:
        grad_out: Gradient w.r.t. output (N, H)
        input_slots: Forward pass input (E*C, H) - needed for weight gradients
        slot_indices: CSR indices (E*C,) - which expert slots contribute to each token
        slot_offsets: CSR offsets (N,) - start position for each token
        slot_counts: CSR counts (N,) - number of contributors per token
        weights: Optional per-slot weights (E*C,) or None
        max_experts: Maximum contributors per token (compile-time constant)
        grad_slots: Gradient w.r.t. input_slots (E*C, H) - output buffer
        grad_weights: Gradient w.r.t. weights (E*C,) - output buffer or None
        add_into: Whether forward used add_into mode (accumulate into shared buffer)
        grad_shared: Gradient w.r.t. shared expert output (N, H) - output buffer, required if add_into=True
        shared_weights: Shared expert weights (N,)
    """
    N, H = grad_out.shape

    # Determine flags
    use_weights = weights is not None
    need_grad_w = grad_weights is not None
    
    use_shared_weights = shared_weights is not None

    # Provide dummy pointer if weights not used (kernel expects a pointer)
    weights_use = weights if use_weights else grad_out  # dummy pointer
    grad_weights_use = grad_weights if need_grad_w else grad_out  # dummy pointer
    input_slots_use = input_slots if need_grad_w else grad_out  # dummy pointer if not needed
    grad_shared_use = grad_shared if add_into else grad_out  # dummy pointer if not add_into
    
    shared_weights_use = shared_weights if use_shared_weights else grad_out # dummy

    def grid(META):
        return (N,)  # Token-parallel: one program per token

    _csr_scatter_bwd_optimized[grid](
        grad_out,
        input_slots_use,
        weights_use,
        slot_indices,
        slot_offsets,
        slot_counts,
        grad_slots,
        grad_weights_use,
        grad_shared_use,
        shared_weights_use,
        MAX_EXPERTS=max_experts,
        NUM_COLUMNS=H,
        USE_WEIGHTS=1 if use_weights else 0,
        NEED_GRAD_W=1 if need_grad_w else 0,
        ADD_INTO=1 if add_into else 0,
        SHARED_WEIGHTS=1 if use_shared_weights else 0,
    )


@csr_scatter_bwd_optimized_compileable.register_fake
def _(
    grad_out: torch.Tensor,
    input_slots: torch.Tensor,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
    weights: Optional[torch.Tensor],
    max_experts: int,
    grad_slots: torch.Tensor,
    grad_weights: Optional[torch.Tensor],
    add_into: bool = False,
    grad_shared: Optional[torch.Tensor] = None,
    shared_weights: Optional[torch.Tensor] = None,
) -> None:
    pass

