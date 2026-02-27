"""Router activation helpers used by MoE routing backends."""
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
    """Return routed weights (and optional shared weights) from router logits."""
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
