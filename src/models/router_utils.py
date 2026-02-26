"""Router activation and utility functions.

This module provides activation functions for MoE routing that operate on
ALL router logits before top-k selection, enabling unified gather-based
weight extraction.
"""
import torch
import torch.nn.functional as F
from torch import Tensor
from typing import Tuple, Optional


def apply_router_activation(
    router_logits: Tensor,
    activation: str,
    G: int = 2,
    include_shared: bool = True
) -> Tuple[Optional[Tensor], Optional[Tensor]]:
    """Apply activation to ALL router logits before top-k selection.

    This unified function handles all activation types. For most activations,
    it computes weights for all (token, expert) pairs, which are later
    gathered at selected positions.

    Args:
        router_logits: (B*T, n_routed_experts) raw router logits
        activation: One of: sigmoid, relu, softmax_k, softmax_e, softmax_e_shared_out
        G: Granularity, used for softmax_e_shared_out (shared weight = 1/G)
        include_shared: Whether to include a shared expert anchor for softmax_e variants

    Returns:
        all_weights: (B*T, n_routed_experts) or None
            - For sigmoid/relu/softmax_e*: activated weights for all positions
            - For softmax_k: None (requires top-k positions, handled separately)
        shared_weights: (B*T,) or None
            - For softmax_e: per-token shared expert weight (from softmax with anchor=0)
            - For softmax_e_shared_out: fixed 1/G per token
            - For softmax_e variants with include_shared=False: None
            - For others: None (shared weight computed via fanout normalization)

    Weight semantics by activation:
        - sigmoid: bounded (0, 1), independent per expert
        - relu: sparse, unbounded positive
        - softmax_k: per-expert normalization (across k selected tokens)
        - softmax_e: per-token normalization (shared IN softmax, anchor=0)
        - softmax_e_shared_out: per-token normalization (shared OUT, fixed 1/G)
    """
    n_tokens = router_logits.shape[0]
    device = router_logits.device
    dtype = router_logits.dtype

    if activation == "sigmoid":
        return torch.sigmoid(router_logits), None

    elif activation == "relu":
        return F.relu(router_logits), None

    elif activation == "softmax_k":
        # Softmax over ALL tokens per expert (dim=0) BEFORE selection
        # Each expert's weights sum to 1 across all tokens
        # Shape: (B*T, n_routed_experts) -> softmax on token dimension
        return F.softmax(router_logits, dim=0), None

    elif activation == "softmax_e":
        if not include_shared:
            return F.softmax(router_logits, dim=-1), None
        # Shared expert IN softmax: compete with routed experts
        # Anchor logit = 0 represents shared expert's "default" contribution
        # Higher routed logits -> lower shared weight, lower routed -> higher shared
        anchor = torch.zeros(n_tokens, 1, device=device, dtype=dtype)
        augmented = torch.cat([anchor, router_logits], dim=-1)  # (B*T, 1 + n_routed)
        all_w = F.softmax(augmented, dim=-1)
        shared_weights = all_w[:, 0]    # (B*T,) - shared expert weight per token
        routed_weights = all_w[:, 1:]   # (B*T, n_routed) - routed expert weights
        return routed_weights, shared_weights

    elif activation == "softmax_e_shared_out":
        if not include_shared:
            return F.softmax(router_logits, dim=-1), None
        # Shared expert OUT of softmax: anchor normalizes routed, but shared weight is fixed 1/G
        # Anchor logit = 0 "steals" some probability from routed experts
        # But shared expert gets fixed 1/G regardless (doesn't use anchor's probability)
        anchor = torch.zeros(n_tokens, 1, device=device, dtype=dtype)
        augmented = torch.cat([anchor, router_logits], dim=-1)  # (B*T, 1 + n_routed)
        all_w = F.softmax(augmented, dim=-1)
        routed_weights = all_w[:, 1:]   # (B*T, n_routed) - routed weights (sum < 1)
        # Shared weight is FIXED 1/G, not from softmax
        shared_weights = torch.full((n_tokens,), 1.0 / G, device=device, dtype=dtype)
        return routed_weights, shared_weights

    else:
        raise ValueError(f"Unknown router_activation: {activation}")


def compute_fanout(
    n_tokens: int,
    indices: Tensor,
    device: torch.device,
    dtype: torch.dtype
) -> Tensor:
    """Count how many experts selected each token.

    Args:
        n_tokens: Total number of tokens (B*T)
        indices: (total_selected,) flattened token indices from all experts
        device: Output device
        dtype: Output dtype

    Returns:
        fanout: (n_tokens,) count of experts that selected each token
    """
    return torch.bincount(indices, minlength=n_tokens).to(dtype)
