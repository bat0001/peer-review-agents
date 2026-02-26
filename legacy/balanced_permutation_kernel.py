"""Sketch of a perfectly balanced MoE permutation kernel.

This file mirrors megablocks/backend/kernels.py but simplifies the routing
path when each expert receives exactly the same number of tokens.
"""

import torch
import triton
import triton.language as tl


@triton.jit
@triton.autotune(
    configs=[
        triton.Config({'BLOCK_X': 64}, num_warps=2),
        triton.Config({'BLOCK_X': 128}, num_warps=2),
        triton.Config({'BLOCK_X': 256}, num_warps=4),
    ],
    key=['NUM_COLUMNS'],
)
# pylint: disable=too-many-arguments
# NOTE: This is a sketch, not drop-in production code.
def _balanced_copy(
    a,
    b,
    indices,
    *,
    NUM_COLUMNS: tl.constexpr,
    CAPACITY: tl.constexpr,
    BLOCK_X: tl.constexpr,
    TOP_K: tl.constexpr,
    A_TO_B: tl.constexpr,
):
    """Stream rows between dense token and expert buffers.

    Compared to megablocks.backend.kernels._padded_copy:
    - No bin_ids/bins/padded_bins arguments.
    - No optional weights scaling.
    - Launch grid is 1-D `(num_experts * CAPACITY,)`.
    """
    prog_id = tl.program_id(0)
    expert_idx = prog_id // CAPACITY
    slot_idx = prog_id % CAPACITY

    index_a = tl.load(indices + prog_id)
    row_a = index_a // TOP_K if A_TO_B else index_a
    row_b = expert_idx * CAPACITY + slot_idx

    a += tl.multiple_of(row_a * NUM_COLUMNS, NUM_COLUMNS)
    b += tl.multiple_of(row_b * NUM_COLUMNS, NUM_COLUMNS)
    offsets = tl.max_contiguous(tl.arange(0, BLOCK_X), BLOCK_X)

    iterations = tl.cdiv(NUM_COLUMNS, BLOCK_X)
    for _ in range(iterations):
        mask = offsets < NUM_COLUMNS
        iptr = a if A_TO_B else b
        optr = b if A_TO_B else a
        x = tl.load(iptr + offsets, mask=mask)
        x = x.to(tl.float32)
        tl.store(optr + offsets, x.to(optr.dtype.element_ty), mask=mask)
        offsets += BLOCK_X


def balanced_binned_gather(
    x: torch.Tensor,
    indices: torch.Tensor,
    *,
    num_experts: int,
    capacity: int,
    top_k: int,
    block_x: int = 128,
):
    """Gather tokens into expert-major blocks assuming perfect balance.

    Args:
        x: Tensor of shape (tokens, hidden).
        indices: Long tensor of shape (tokens * top_k,) already grouped by expert.
        num_experts: Number of experts; must satisfy `num_experts * capacity == tokens * top_k`.
        capacity: Tokens per expert (no padding / no drops).
        top_k: Router fan-out so the kernel can collapse duplicates on gather.
        block_x: Triton tile width for the hidden dimension.
    """
    assert indices.shape[0] == num_experts * capacity
    out = torch.empty((num_experts, capacity, x.shape[1]), dtype=x.dtype, device=x.device)
    _balanced_copy[(indices.shape[0],)](
        x,
        out,
        indices,
        NUM_COLUMNS=x.shape[1],
        CAPACITY=capacity,
        BLOCK_X=block_x,
        TOP_K=top_k,
        A_TO_B=True,
    )
    return out


def balanced_binned_scatter(
    x: torch.Tensor,
    indices: torch.Tensor,
    *,
    num_experts: int,
    capacity: int,
    top_k: int,
    block_x: int = 128,
):
    """Scatter expert outputs back to the original token order."""
    tokens = indices.shape[0] // top_k
    out = torch.empty((tokens, top_k, x.shape[-1]), dtype=x.dtype, device=x.device)
    _balanced_copy[(indices.shape[0],)](
        out,
        x,
        indices,
        NUM_COLUMNS=x.shape[-1],
        CAPACITY=capacity,
        BLOCK_X=block_x,
        TOP_K=top_k,
        A_TO_B=False,
    )
    return out.sum(dim=1) if top_k > 1 else out.view(tokens, x.shape[-1])


@triton.jit
@triton.autotune(
    configs=[
        triton.Config({'BLOCK_X': 64}, num_warps=2),
        triton.Config({'BLOCK_X': 128}, num_warps=2),
        triton.Config({'BLOCK_X': 256}, num_warps=4),
    ],
    key=['NUM_COLUMNS'],
)
def _balanced_scatter_atomic(
    expert_out,
    indices,
    out,
    *,
    NUM_COLUMNS: tl.constexpr,
    CAPACITY: tl.constexpr,
    BLOCK_X: tl.constexpr,
):
    """Accumulate expert outputs back into the dense token tensor.

    Tokens may appear multiple times across experts; we rely on atomics to
    resolve collisions. This mirrors `output.index_add_` in models/gec.py but
    issues coalesced vector atomics per hidden tile.
    """
    prog_id = tl.program_id(0)
    expert_idx = prog_id // CAPACITY
    slot_idx = prog_id % CAPACITY

    token = tl.load(indices + prog_id)

    expert_out += tl.multiple_of((expert_idx * CAPACITY + slot_idx) * NUM_COLUMNS, NUM_COLUMNS)
    out += tl.multiple_of(token * NUM_COLUMNS, NUM_COLUMNS)
    offsets = tl.max_contiguous(tl.arange(0, BLOCK_X), BLOCK_X)

    iterations = tl.cdiv(NUM_COLUMNS, BLOCK_X)
    for _ in range(iterations):
        mask = offsets < NUM_COLUMNS
        x = tl.load(expert_out + offsets, mask=mask).to(tl.float32)
        tl.atomic_add(out + offsets, x, mask=mask)
        offsets += BLOCK_X


def balanced_scatter_atomic(
    expert_out: torch.Tensor,
    indices: torch.Tensor,
    *,
    num_experts: int,
    capacity: int,
    block_x: int = 128,
    out: torch.Tensor,
):
    """Atomic scatter that matches `output.index_add_` semantics."""
    assert expert_out.shape == (num_experts, capacity, out.shape[-1])
    flat = expert_out.view(-1, expert_out.shape[-1])
    _balanced_scatter_atomic[(indices.shape[0],)](
        flat,
        indices,
        out,
        NUM_COLUMNS=out.shape[-1],
        CAPACITY=capacity,
        BLOCK_X=block_x,
    )
    return out

def build_expert_major_indices(token_scores: torch.Tensor, k: int) -> torch.Tensor:
    """Select top-k tokens per expert and flatten in expert-major order.

    Args:
        token_scores: Tensor of shape (num_experts, num_tokens).
        k: Number of tokens per expert.

    Returns:
        Long tensor of shape (num_experts * k,) grouped by expert.
    """
    topk = torch.topk(token_scores, k=k, dim=1, largest=True, sorted=True)
    return topk.indices.reshape(-1)
