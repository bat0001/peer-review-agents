"""
A scatter kernel that combines the output of experts using a sequential add approach.

The goal is to 
- Read once
- Write once
- Avoid atomic adds
"""

import torch
import triton
import triton.language as tl


def _build_inverse_indices(indices: torch.Tensor, num_tokens: int, max_experts: int) -> torch.Tensor:
    """
    Build inverse indices from indices.

    The indices probably comes from a topk operation.
    e.g.
    ```python
    >>> MAX_EXPERTS = 16 
    >>> NUM_TOKENS = 131072
    >>> CAPACITY = 16384
    >>> router_logits = torch.randn(NUM_TOKENS, MAX_EXPERTS)
    >>> topk_values, topk_indices = torch.topk(router_logits, k=10, dim=1)
    >>> inverse_indices = _build_inverse_indices(topk_indices, num_tokens=NUM_TOKENS, max_experts=MAX_EXPERTS)
    ```

    input:
        indices: int32: (num_experts, capacity) - for each expert, which tokens it selected
        num_tokens: int - total number of tokens
        max_experts: int - maximum number of experts that can select any token
    output:
        inverse_indices: int32: (num_tokens, MAX_EXPERTS) linear indices into expert-major buffer. Empty slots marked with -1.
    """
    num_experts, capacity = indices.shape
    device = indices.device

    # Initialize with -1 (empty slots)
    inverse_indices = torch.full((num_tokens, max_experts), -1, dtype=torch.int32, device=device)

    # Compute linear indices for each expert-capacity pair
    linear_idx = torch.arange(num_experts * capacity, device=device, dtype=torch.int32).view(num_experts, capacity)

    # Flatten both arrays
    token_flat = indices.flatten()  # (E*C,) - which token each entry corresponds to
    linear_flat = linear_idx.flatten()  # (E*C,) - linear index in expert-major buffer

    # Sort by token ID to group assignments to the same token
    sort_idx = torch.argsort(token_flat, stable=True)
    tokens_sorted = token_flat[sort_idx]
    linears_sorted = linear_flat[sort_idx]

    # Compute slot index (0, 1, 2, ... for each token, resetting at new token)
    # is_new_token marks boundaries where token ID changes
    is_new_token = torch.cat([
        torch.ones(1, dtype=torch.bool, device=device),
        tokens_sorted[1:] != tokens_sorted[:-1]
    ])
    slot_starts = torch.where(is_new_token)[0]
    # For each position, find which "group" it belongs to and compute offset from group start
    group_ids = torch.searchsorted(slot_starts, torch.arange(len(tokens_sorted), device=device), right=True) - 1
    slot_idx = torch.arange(len(tokens_sorted), device=device) - slot_starts[group_ids]

    # Scatter into output: for each token, fill its slots with linear indices
    inverse_indices[tokens_sorted, slot_idx] = linears_sorted

    return inverse_indices

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
    a, # input: bf16: (MAX_EXPERTS, capacity, hidden_size)
    b, # output: bf16: (num_tokens, hidden_size)
    inverse_indices, # int32: (num_tokens, MAX_EXPERTS) linear indices (0 to MAX_EXPERTS*capacity-1) into expert-major buffer. Empty slots marked with -1.
    weights, # bf16: (MAX_EXPERTS, capacity,) optional scaling weights
    MAX_EXPERTS: tl.constexpr,
    NUM_COLUMNS: tl.constexpr,
    BLOCK_X: tl.constexpr,
    SCALE: tl.constexpr, # if weights
    ADD_INTO: tl.constexpr, # if ADD_INTO is True, we load the token output and accumulate to it. If False, we overwrite the token output.
):
    """Sequential add kernel.
    
    """

    pid = tl.program_id(0)

    # Load all expert indices for this token (shape: [MAX_EXPERTS])
    slot_offsets = tl.arange(0, MAX_EXPERTS)
    expert_indices = tl.load(inverse_indices + pid * MAX_EXPERTS + slot_offsets)

    block_offsets = tl.arange(0, BLOCK_X)
    token_row = b + pid * NUM_COLUMNS

    for col in range(0, NUM_COLUMNS, BLOCK_X):
        offsets = col + block_offsets
        mask = offsets < NUM_COLUMNS
        token_ptr = token_row + offsets

        if ADD_INTO:
            acc = tl.load(token_ptr, mask=mask, other=0).to(tl.float32)
        else:
            acc = tl.zeros([BLOCK_X], dtype=tl.float32)

        # Sequentially accumulate contributions from each expert slot
        for slot in tl.static_range(MAX_EXPERTS):
            # Extract the linear index for this slot using tl.sum to reduce
            expert_linear = tl.sum(tl.where(slot_offsets == slot, expert_indices, 0))

            # Skip if this slot is empty (-1 marker)
            # Use conditional to avoid unnecessary loads
            is_valid = expert_linear != -1

            if is_valid:
                expert_ptr = a + expert_linear * NUM_COLUMNS + offsets
                x = tl.load(expert_ptr, mask=mask, other=0.0).to(tl.float32)
                if SCALE:
                    weight = tl.load(weights + expert_linear).to(tl.float32)
                    x = x * weight
                acc += x

        tl.store(token_ptr, acc.to(b.dtype.element_ty), mask=mask)