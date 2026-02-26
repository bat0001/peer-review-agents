"""CSR (Compressed Sparse Row) infrastructure for token-parallel scatter.

Unlike Token Choice models (TC), Expert Choice models (EC) may have variable number of experts per token. Naive implementation uses index_add for accumulation, causing multiple writes to the same token with atomic adds. 

Instead, we build a scatter_sum kernel to make sure we only read and write once per token. We launch one program per token and accumulate contributions from up to MAX_EXPERTS experts.

Key components:
- build_slot_indices: Converts expert-major indices to token-major CSR format
- _csr_scatter_sum: Triton kernel for token-parallel scatter-reduce
"""

from __future__ import annotations

from typing import Tuple, Optional

import torch
import torch.library
import triton
import triton.language as tl


@torch.no_grad()
def build_slot_indices(
    indices: torch.Tensor,
    num_tokens: int,
    max_experts: int
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Build CSR format for token-major scatter from expert-major indices.

    Converts expert-major routing indices to a CSR (Compressed Sparse Row)
    representation suitable for token-parallel scatter operations. Each token
    accumulates contributions from multiple experts; this function builds the
    data structure to efficiently enumerate those contributors.

    Assumes:
        - No -1 entries in indices (all slots are valid)
        - No token has more than max_experts contributors, because the selected token for each expert is non-repeating

    Args:
        indices: Expert-major indices [E, C] where indices[e, s] is the token
                 id routed to expert e at capacity slot s
        num_tokens: Total number of tokens (N)
        max_experts: Maximum contributors per token (compile-time bound for kernel)

    Notations: 
    - E: number of experts
    - C: number of capacity slots per expert
    - N: number of tokens
    - H: hidden dimension size (not used in this function)

    Returns:
        Tuple of:
        - slot_indices: int32 [E*C] - Linear indices in E*C space
        - slot_offsets: int32 [N] - Start offset in slot_indices for each token
        - slot_counts: int32 [N] - Number of contributors per token

    The function performs a stable sort by token id, which preserves the
    expert/capacity order within each token.

    Example:
        E=4, N=4, C=2
        indices = [[0, 2],    # expert 0 processes tokens 0, 2
                   [0, 1],    # expert 1 processes tokens 0, 1
                   [1, 2],    # expert 2 processes tokens 1, 2
                   [2, 3]]    # expert 3 processes tokens 2, 3

        token_flat = [0, 2, 0, 1, 1, 2, 2, 3]  # flattened tokens
        linear_flat = [0, 1, 2, 3, 4, 5, 6, 7]  # slot indices

        After stable sort by token_flat:
        token_flat = [0, 0, 1, 1, 2, 2, 2, 3]
        linear_flat = [0, 2, 3, 4, 1, 5, 6, 7]

        Output:
        slot_indices = [0, 2, 3, 4, 1, 5, 6, 7]  # which slots contribute
        slot_counts = [2, 2, 3, 1]               # each token has 2 contributors
        prefix = [2, 4, 7, 8]
        slot_offsets = [0, 2, 4, 7]              # token 0 starts at 0, token 1 at 2, etc.
    """
    assert indices.dim() == 2, f"Expected 2D indices [E, C], got shape {indices.shape}"
    E, C = indices.shape
    device = indices.device

    # Flatten to (E*C,) and create linear indices
    token_flat = indices.reshape(-1).to(torch.int32)  # (E*C,)
    linear_flat = torch.arange(E * C, device=device, dtype=torch.int32)  # (E*C,)

    # Stable sort by token id (preserves expert/capacity order within token)
    sort_idx = torch.argsort(token_flat, stable=True)
    token_flat = token_flat[sort_idx]
    slot_indices = linear_flat[sort_idx]

    # Build CSR arrays
    slot_counts = torch.bincount(token_flat, minlength=num_tokens).to(torch.int32)
    prefix = torch.cumsum(slot_counts, dim=0)
    slot_offsets = (prefix - slot_counts).to(torch.int32)
    return slot_indices, slot_offsets, slot_counts


@torch.no_grad()
def build_slot_indices_flat(
    indices_flat: torch.Tensor,
    num_tokens: int,
    max_experts: int
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Build CSR format from flat token indices (no E, C structure).

    This is a simpler version of build_slot_indices for the flat API where
    indices are already flattened (total_active,) rather than batched (E, C).

    Args:
        indices_flat: Flat token indices (total_active,) where each entry is a token id
        num_tokens: Total number of tokens (N)
        max_experts: Maximum contributors per token (compile-time bound for kernel)

    Returns:
        Tuple of:
        - slot_indices: int32 (total_active,) - Reordering indices for h_flat
        - slot_offsets: int32 (N,) - Start offset in slot_indices for each token
        - slot_counts: int32 (N,) - Number of contributors per token

    Example:
        indices_flat = [0, 2, 0, 1, 1, 2, 2, 3]  # 8 slots, tokens 0-3

        After stable sort by token id:
        sorted_tokens = [0, 0, 1, 1, 2, 2, 2, 3]
        slot_indices = [0, 2, 3, 4, 1, 5, 6, 7]  # original positions

        Output:
        slot_indices = [0, 2, 3, 4, 1, 5, 6, 7]
        slot_counts = [2, 2, 3, 1]
        slot_offsets = [0, 2, 4, 7]
    """
    device = indices_flat.device
    total_active = indices_flat.shape[0]

    if total_active == 0:
        # Handle empty case
        slot_indices = torch.zeros(0, device=device, dtype=torch.int32)
        slot_counts = torch.zeros(num_tokens, device=device, dtype=torch.int32)
        slot_offsets = torch.zeros(num_tokens, device=device, dtype=torch.int32)
        return slot_indices, slot_offsets, slot_counts

    # Convert to int32 for sorting
    token_flat = indices_flat.to(torch.int32)
    linear_flat = torch.arange(total_active, device=device, dtype=torch.int32)

    # Stable sort by token id (preserves order within each token)
    sort_idx = torch.argsort(token_flat, stable=True)
    slot_indices = linear_flat[sort_idx]

    # Build CSR arrays
    slot_counts = torch.bincount(token_flat, minlength=num_tokens).to(torch.int32)
    prefix = torch.cumsum(slot_counts, dim=0)
    slot_offsets = (prefix - slot_counts).to(torch.int32)

    return slot_indices, slot_offsets, slot_counts


@triton.autotune(
    configs=[
        triton.Config({'BLOCK_X': 64}, num_warps=2),
        triton.Config({'BLOCK_X': 128}, num_warps=2),
        triton.Config({'BLOCK_X': 256}, num_warps=2),
        triton.Config({'BLOCK_X': 128}, num_warps=4),
        triton.Config({'BLOCK_X': 256}, num_warps=4),
    ],
    key=['NUM_COLUMNS', 'MAX_EXPERTS'],
)
@triton.jit
def _csr_scatter_sum(
    expert_slots,      # bf16: flattened (E*C, H)
    token_out,         # bf16: (N, H)
    slot_indices,      # int32: (E*C,)
    slot_offsets,      # int32: (N,)
    slot_counts,       # int32: (N,)
    weights,           # bf16: (E*C,) optional; ignored if USE_WEIGHTS == 0  # QUESTION: sure not fp32?
    MAX_EXPERTS: tl.constexpr,
    NUM_COLUMNS: tl.constexpr,
    BLOCK_X: tl.constexpr,
    USE_WEIGHTS: tl.constexpr,    # 0 or 1
    ACCUMULATE: tl.constexpr,      # 0 or 1
    SHARED_EXPERT_WEIGHTS: tl.constexpr, # 0 or 1
    shared_expert_weights = None, # bf16: (N,) optional; ignored if SHARED_EXPERT_WEIGHTS == 0
):
    """Token-parallel CSR scatter-reduce kernel.

    Each program handles one token and accumulates contributions from up to
    MAX_EXPERTS expert slots. This is the core kernel for the CSR scatter
    operation.

    Grid: (num_tokens,) - one program per token

    Why token-parallel instead of expert-parallel?
    - Token-parallel: Each token does 1 read + 1 write = O(H) memory operations
    - Expert-parallel: Multiple experts write to same token → atomic adds with
      contention = O(E*H) memory operations
    - For Expert Choice with variable experts/token, token-parallel avoids atomics
      and scales better

    Args:
        expert_slots: Expert outputs in flattened (E*C, H) layout
        token_out: Output buffer (N, H)
        slot_indices: CSR indices (E*C,) - which expert slots contribute to each token
        slot_offsets: CSR offsets (N,) - start position for each token
        slot_counts: CSR counts (N,) - number of contributors per token
        weights: Optional per-slot weights (E*C,)
        MAX_EXPERTS: Compile-time max contributors per token
        NUM_COLUMNS: Hidden dimension size (H)
        BLOCK_X: Block size for column dimension
        USE_WEIGHTS: Whether to apply per-slot weights (0 or 1)
        ACCUMULATE: Whether to add to existing buffer (0 or 1)

    Example: Token 0 with 2 contributing experts at different capacity slots
        Setup: E=2 experts, C=5 capacity/expert, H=4 hidden dim, MAX_EXPERTS=4
        Token 0 is routed to:
        - Expert 0, capacity slot 1 → linear index = 0*5 + 1 = 1 in (E*C) space
        - Expert 1, capacity slot 3 → linear index = 1*5 + 3 = 8 in (E*C) space

        CSR data: slot_indices = [1, 8, ...], slot_offsets[0] = 0, slot_counts[0] = 2
    """
    # === Program for token 0 ===
    pid = tl.program_id(0)  # token id = 0
    start = tl.load(slot_offsets + pid)  # start = 0
    count = tl.load(slot_counts + pid)   # count = 2

    # col_ids = [0, 1, 2, 3]  (BLOCK_X=4)
    col_ids = tl.arange(0, BLOCK_X)
    # token_row = pointer to start of token 0's output row
    token_row = token_out + pid * NUM_COLUMNS

    if SHARED_EXPERT_WEIGHTS:
        shared_expert_weights_val = tl.load(shared_expert_weights + pid)
    

    # Loop over hidden dimension in blocks (H=4, BLOCK_X=4 → single iteration)
    # col=0: process columns [0,1,2,3]
    for col in range(0, NUM_COLUMNS, BLOCK_X):
        # offs = [0, 1, 2, 3]  (column indices within H)
        offs = col + col_ids
        col_mask = offs < NUM_COLUMNS
        out_ptr = token_row + offs

        # Initialize accumulator
        if ACCUMULATE:
            acc = tl.load(out_ptr, mask=col_mask, other=0).to(tl.float32)
            if SHARED_EXPERT_WEIGHTS:
                acc *= shared_expert_weights_val
        else:
            acc = tl.zeros([BLOCK_X], dtype=tl.float32)

        # === DYNAMIC LOOP: Process only contributing experts ===
        # Loop through up to MAX_EXPERTS (compile-time constant)
        # Only execute work for valid experts (expert_idx < count)
        for expert_idx in range(MAX_EXPERTS):
            # Only process valid experts - use if-statement to guard all operations
            if expert_idx < count:
                # Load this expert's slot index
                # expert_idx=0: lin=1 (expert 0, slot 1)
                # expert_idx=1: lin=8 (expert 1, slot 3)
                lin = tl.load(slot_indices + start + expert_idx)
                base = lin * NUM_COLUMNS  # base = {4, 32} for experts {0, 1}

                # Load this expert's contribution for current column block
                # ptrs = expert_slots + base + [0, 1, 2, 3]
                # expert_idx=0: [ptr+4, ptr+5, ptr+6, ptr+7]
                # expert_idx=1: [ptr+32, ptr+33, ptr+34, ptr+35]
                expert_ptr = expert_slots + base + offs
                x = tl.load(expert_ptr, mask=col_mask, other=0.0).to(tl.float32)

                # Apply weight if enabled
                if USE_WEIGHTS:
                    w = tl.load(weights + lin).to(tl.float32)
                    x = x * w

                # Accumulate this expert's contribution
                acc += x

        # Store result
        tl.store(out_ptr, acc.to(token_out.dtype.element_ty), mask=col_mask)


@torch.library.custom_op("nanogec::csr_scatter_sum", mutates_args={"token_out"})
def csr_scatter_sum_compileable(
    expert_slots: torch.Tensor,
    token_out: torch.Tensor,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
    weights: Optional[torch.Tensor],
    max_experts: int,
    use_weights: bool,
    accumulate: bool,
    shared_expert_weights: Optional[torch.Tensor] = None,
) -> None:
    """Wrapped Triton kernel for compilation visibility.

    Args:
        expert_slots: Expert outputs (E*C, H)
        token_out: Output buffer (N, H) - may contain shared expert output if accumulate=True
        slot_indices: CSR indices (E*C,)
        slot_offsets: CSR offsets (N,)
        slot_counts: CSR counts (N,)
        weights: Per-slot weights (E*C,) for routed experts
        max_experts: Maximum contributors per token
        use_weights: Whether to apply per-slot weights
        accumulate: Whether to add to existing buffer (for shared expert fusion)
        shared_expert_weights: Per-token weights (N,) to apply to existing buffer content
                               Only used when accumulate=True. If None, existing buffer
                               is assumed to be pre-weighted.
    """
    N, H = token_out.shape

    def grid(META):
        return (N,)

    _csr_scatter_sum[grid](
        expert_slots,
        token_out,
        slot_indices,
        slot_offsets,
        slot_counts,
        weights if weights is not None else expert_slots,  # dummy pointer
        MAX_EXPERTS=max_experts,
        NUM_COLUMNS=H,
        USE_WEIGHTS=1 if use_weights else 0,
        ACCUMULATE=1 if accumulate else 0,
        SHARED_EXPERT_WEIGHTS=1 if shared_expert_weights is not None else 0,
        shared_expert_weights=shared_expert_weights if shared_expert_weights is not None else weights,  # dummy pointer
    )

# Register fake for strict compilability
@csr_scatter_sum_compileable.register_fake
def _(
    expert_slots: torch.Tensor,
    token_out: torch.Tensor,
    slot_indices: torch.Tensor,
    slot_offsets: torch.Tensor,
    slot_counts: torch.Tensor,
    weights: Optional[torch.Tensor],
    max_experts: int,
    use_weights: bool,
    accumulate: bool,
    shared_expert_weights: Optional[torch.Tensor] = None,
) -> None:
    pass

# -------------------------------------------------------------------------
# Fused Backward Kernel (Task 2)
# -------------------------------------------------------------------------

@triton.autotune(
    configs=[
        triton.Config({'BLOCK_X': 256}, num_warps=2),
        triton.Config({'BLOCK_X': 256}, num_warps=4),
        triton.Config({'BLOCK_X': 256}, num_warps=8),
        triton.Config({'BLOCK_X': 256}, num_warps=2, num_stages=2),
        triton.Config({'BLOCK_X': 256}, num_warps=4, num_stages=2),
        triton.Config({'BLOCK_X': 256}, num_warps=8, num_stages=2),
        triton.Config({'BLOCK_X': 256}, num_warps=2, num_stages=3),
        triton.Config({'BLOCK_X': 256}, num_warps=4, num_stages=3),
        triton.Config({'BLOCK_X': 256}, num_warps=8, num_stages=3),
        triton.Config({'BLOCK_X': 256}, num_warps=2, num_stages=4),
        triton.Config({'BLOCK_X': 256}, num_warps=4, num_stages=4),
        triton.Config({'BLOCK_X': 256}, num_warps=8, num_stages=4),
    ],
    key=['NUM_COLUMNS', 'MAX_EXPERTS'],
)
@triton.jit
def _csr_scatter_bwd(
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
    BLOCK_X: tl.constexpr,
    USE_WEIGHTS: tl.constexpr,
    NEED_GRAD_W: tl.constexpr,
    ADD_INTO: tl.constexpr,
    SHARED_WEIGHTS: tl.constexpr,
):
    """
    Backward: Gather gradients from tokens to slots.
    Parallelism: Token-Parallel (one program per token).
    
    Strategy:
    - We launch 1 program per token.
    - We iterate over the experts contributing to this token.
    - Inside the expert loop, we iterate over columns to compute full row gradients.
    - Since 'grad_out[token]' is reused for all experts, it stays in L1 cache.
    """
    pid = tl.program_id(0)
    
    # 1. CSR Setup
    start = tl.load(slot_offsets_ptr + pid)
    count = tl.load(slot_counts_ptr + pid)
    
    grad_out_row = grad_out_ptr + pid * NUM_COLUMNS

    # 2. Loop over Experts (Outer Loop for better grad_w reduction)
    # Note: we don't need to maintain the accumulator this way
    for i in range(MAX_EXPERTS):
        if i < count:
            # Which slot are we handling?
            slot_idx = tl.load(slot_indices_ptr + start + i)
            
            # Load weight once
            w_val = 1.0
            if USE_WEIGHTS:
                w_val = tl.load(weights_ptr + slot_idx).to(tl.float32)
            
            # Pointers for this slot
            grad_slots_row = grad_slots_ptr + slot_idx * NUM_COLUMNS
            input_slots_row = input_slots_ptr + slot_idx * NUM_COLUMNS
            
            # Accumulator for grad_w (scalar reduction over H)
            dot_accum = 0.0
            
            # 3. Loop over Columns (Hidden Dim)
            for col_start in range(0, NUM_COLUMNS, BLOCK_X):
                offsets = col_start + tl.arange(0, BLOCK_X)
                mask = offsets < NUM_COLUMNS
                
                # Load Gradient from Token (L1 Cached reuse)
                g = tl.load(grad_out_row + offsets, mask=mask, other=0.0).to(tl.float32)
                
                # --- Compute grad_x = grad_out * weight ---
                d_slot = g * w_val
                tl.store(grad_slots_row + offsets, d_slot.to(grad_slots_ptr.dtype.element_ty), mask=mask)
                
                # --- Compute grad_w = dot(grad_out, input_slot) ---
                if NEED_GRAD_W:
                    x = tl.load(input_slots_row + offsets, mask=mask, other=0.0).to(tl.float32)
                    dot_accum += tl.sum(g * x)
            
            # 4. Store Weight Gradient
            if NEED_GRAD_W:
                tl.store(grad_weights_ptr + slot_idx, dot_accum.to(grad_weights_ptr.dtype.element_ty))

    # 5. Compute grad_shared = grad_out * shared_weights
    if ADD_INTO:
        grad_shared_row = grad_shared_ptr + pid * NUM_COLUMNS
        
        sw_val = 1.0
        if SHARED_WEIGHTS:
            sw_val = tl.load(shared_weights_ptr + pid).to(tl.float32)
            
        for col_start in range(0, NUM_COLUMNS, BLOCK_X):
            offsets = col_start + tl.arange(0, BLOCK_X)
            mask = offsets < NUM_COLUMNS
            
            g = tl.load(grad_out_row + offsets, mask=mask, other=0.0).to(tl.float32)
            d_shared = g * sw_val
            tl.store(grad_shared_row + offsets, d_shared.to(grad_shared_ptr.dtype.element_ty), mask=mask)

@torch.library.custom_op("nanogec::scatter_backward", mutates_args={"grad_slots", "grad_weights"})
def csr_scatter_bwd_compileable(
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
    """CSR-based backward pass wrapper for token-parallel gradient computation.

    Token-parallel strategy: One program per token, iterates over contributing experts.

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
        add_into: Whether forward used add_into mode
        grad_shared: Gradient w.r.t. shared expert output (N, H) - output buffer
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
    grad_shared_use = grad_shared if add_into else grad_out
    shared_weights_use = shared_weights if use_shared_weights else grad_out

    def grid(META):
        return (N,)  # Token-parallel: one program per token

    _csr_scatter_bwd[grid](
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

@csr_scatter_bwd_compileable.register_fake
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

__all__ = ['build_slot_indices', 'build_slot_indices_flat', '_csr_scatter_sum',
           'csr_scatter_sum_compileable', '_csr_scatter_bwd', 'csr_scatter_bwd_compileable']
