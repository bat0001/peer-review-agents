"""
A second scatter kernel that combines the output of experts using a sequential add approach.

The goal is to 
- Read once
- Write once
- Avoid atomic adds

Compared to the original sequential @src/kernels/sequential.py, this uses a more compact indexing
"""

import torch
import triton
import triton.language as tl


@torch.no_grad()
def _build_inverse_indices(indices: torch.Tensor, num_tokens: int, max_experts: int):
    """
    Build inverse indices from indices.

    The indices probably comes from a topk operation.
    e.g.
    ```python
    >>> MAX_EXPERTS = 16 # E
    >>> NUM_TOKENS = 131072 # N
    >>> CAPACITY = 16384 # C
    >>> router_logits = torch.randn(NUM_TOKENS, MAX_EXPERTS)
    >>> topk_values, topk_indices = torch.topk(router_logits, k=10, dim=1)
    >>> inverse_indices, index_offsets, expert_counts = _build_inverse_indices(topk_indices, num_tokens=NUM_TOKENS, max_experts=MAX_EXPERTS)
    ```

    input:
        indices: int32/int64: (num_experts, capacity) - for each expert, which tokens it selected (or -1 for empty)
        num_tokens: int - total number of tokens
        max_experts: int - maximum number of experts that can select any token
    output:
        inverse_indices: int32: (K,) - linear indices into expert-major buffer, K = sum of expert_counts
        index_offsets: int32: (num_tokens,) - start offset in inverse_indices for each token
        expert_counts: int32: (num_tokens,) - number of contributors for each token
    """
    assert indices.dim() == 2
    num_experts, capacity = indices.shape
    device = indices.device

    token_flat = indices.reshape(-1).to(torch.int64)                                    # (E*C,)
    linear_flat = torch.arange(num_experts * capacity, device=device, dtype=torch.int64) # (E*C,)

    # keep only valid token ids
    valid = (token_flat >= 0) & (token_flat < num_tokens)
    token_flat = token_flat[valid]
    linear_flat = linear_flat[valid]

    if token_flat.numel() == 0:
        inverse_indices = torch.empty(0, dtype=torch.int32, device=device)
        index_offsets = torch.zeros(num_tokens, dtype=torch.int32, device=device)
        expert_counts = torch.zeros(num_tokens, dtype=torch.int32, device=device)
        return inverse_indices, index_offsets, expert_counts

    # stable sort by token to group contributors per token deterministically
    sort_idx = torch.argsort(token_flat, stable=True)
    token_flat = token_flat[sort_idx]
    linear_flat = linear_flat[sort_idx]

    # cap per-token contributors at max_experts (deterministic drop)
    is_new = torch.ones_like(token_flat, dtype=torch.bool)
    is_new[1:] = token_flat[1:] != token_flat[:-1]
    starts = torch.where(is_new)[0]
    gid = torch.searchsorted(starts, torch.arange(token_flat.numel(), device=device), right=True) - 1
    slot = torch.arange(token_flat.numel(), device=device) - starts[gid]
    keep = slot < max_experts
    token_flat = token_flat[keep]
    linear_flat = linear_flat[keep]

    # counts and offsets
    expert_counts = torch.bincount(token_flat, minlength=num_tokens).to(torch.int32)       # (num_tokens,)
    if num_tokens > 0:
        c64 = expert_counts.to(torch.int64)
        prefix = torch.cumsum(c64, dim=0)                                                  # inclusive
        index_offsets = (prefix - c64).to(torch.int32)                                     # exclusive
    else:
        index_offsets = torch.empty(0, dtype=torch.int32, device=device)

    inverse_indices = linear_flat.to(torch.int32)
    return inverse_indices, index_offsets, expert_counts 

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
def _sequential_add(
    a,                 # bf16: flattened (E*C, H)    — rows addressable by linear index
    b,                 # bf16: (N, H)
    inverse_indices,   # int32: (K,)  contributors sorted by token
    index_offsets,     # int32: (N,)  start offset in inverse_indices for token t
    expert_counts,     # int32: (N,)
    weights,           # bf16: (E*C,) optional; ignored if SCALE == 0
    MAX_EXPERTS: tl.constexpr,
    NUM_COLUMNS: tl.constexpr,
    BLOCK_X: tl.constexpr,
    SCALE: tl.constexpr,    # 0 or 1
    ADD_INTO: tl.constexpr, # 0 or 1
):
    """Sequential add kernel using CSR-style indexing.
    
    """
    pid = tl.program_id(0)  # token id in [0, N)

    # Per-token CSR slice: start + count (both scalars)
    start = tl.load(index_offsets + pid)
    count = tl.load(expert_counts + pid)

    # Prepare slot ids [0..MAX_EXPERTS-1] and mask to the actual count
    slot_ids = tl.arange(0, MAX_EXPERTS)
    slot_mask = slot_ids < count

    # Load the contributing row indices once per token
    lins = tl.load(inverse_indices + start + slot_ids, mask=slot_mask, other=0)      # [MAX_EXPERTS]
    bases = lins * NUM_COLUMNS                                                        # [MAX_EXPERTS]
    if SCALE:
        w = tl.load(weights + lins, mask=slot_mask, other=0.0).to(tl.float32)        # [MAX_EXPERTS]

    # Process the hidden dimension in BLOCK_X stripes
    col_ids = tl.arange(0, BLOCK_X)
    token_row = b + pid * NUM_COLUMNS

    for col in range(0, NUM_COLUMNS, BLOCK_X):
        offs = col + col_ids
        col_mask = offs < NUM_COLUMNS
        out_ptr = token_row + offs

        if ADD_INTO:
            acc = tl.load(out_ptr, mask=col_mask, other=0).to(tl.float32)
        else:
            acc = tl.zeros([BLOCK_X], dtype=tl.float32)

        # 2D pointers: [slots, columns]
        # Each row points to one expert row; each column advances along hidden size.
        ptrs = a + bases[:, None] + offs[None, :]
        m = slot_mask[:, None] & col_mask[None, :]

        x = tl.load(ptrs, mask=m, other=0.0).to(tl.float32)        # [MAX_EXPERTS, BLOCK_X]
        if SCALE:
            x = x * w[:, None]                                     # broadcast per-slot weights
        acc += tl.sum(x, axis=0)                                   # reduce over slots

        tl.store(out_ptr, acc.to(b.dtype.element_ty), mask=col_mask)