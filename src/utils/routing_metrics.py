"""Routing metrics computation for GEC/EC models."""

from typing import Dict, Optional, Any
import torch


def compute_routing_metrics(
    cutoffs: torch.Tensor,
    cutoff_ema: torch.Tensor,
    weights: torch.Tensor,
    router_logits_flat: torch.Tensor,
    token_fanout: torch.Tensor,
    expert_usage: torch.Tensor,
    layer_idx: int,
    n_layer: int,
    model_instance: Optional[Any] = None,
    router_activation: str = "sigmoid",
    normalizer: Optional[torch.Tensor] = None,
    indices: Optional[torch.Tensor] = None,
    above_counts: Optional[torch.Tensor] = None,
    k_min: Optional[int] = None,
    k_max: Optional[int] = None,
    n_tokens: Optional[int] = None,
) -> Dict[str, torch.Tensor]:
    """
    Compute all common routing metrics (unified across GEC/EC/GEC_shared).

    All metric names are identical across models (no prefixes).
    Model identification via wandb run config/name.

    Args:
        cutoffs: Current routing cutoffs (n_experts,) or (n_chunks, n_experts)
        cutoff_ema: Effective (bias-corrected) cutoff EMA used for routing (n_experts,)
        weights: Activated router weights (flattened)
        router_logits_flat: All router logits (n_tokens, n_experts)
        token_fanout: Expert count per token (n_tokens,)
        expert_usage: Fraction of tokens per expert (n_experts,)
        layer_idx: Current layer index
        n_layer: Total number of layers
        model_instance: Optional model instance for temporal tracking
        router_activation: Router activation type
        normalizer: Optional per-token normalization factors (n_tokens,) for norm metrics
        indices: Optional selected token indices (flattened) for norm metrics
        above_counts: Optional natural token counts before capacity constraints (n_experts,)
        k_min: Optional lower capacity bound (scalar)
        k_max: Optional upper capacity bound (scalar)
        n_tokens: Optional total token count for capacity metrics (for EP where above_counts is global)

    Returns:
        Dict of metrics (see memory/plans/router_metrics.md for complete list)

    Temporal metrics require buffers in model_instance:
        - cutoff_history_L{i}: (temporal_window, n_experts)
        - history_idx_L{i}: scalar tensor
        - prev_cutoff_L{i}: (n_experts,)
    """
    metrics = {}

    # Average cutoffs across chunks if needed
    cutoffs_avg = cutoffs.mean(dim=0) if cutoffs.ndim == 2 else cutoffs

    # Global routing metrics
    metrics['expert_usage'] = expert_usage
    metrics['avg_experts_per_token'] = token_fanout.mean()
    metrics['max_experts_per_token'] = token_fanout.max()
    metrics['tokens_with_no_expert'] = (token_fanout == 0).float().mean()
    metrics['tokens_with_1_expert'] = (token_fanout == 1).float().mean()
    metrics['tokens_with_2+_experts'] = (token_fanout >= 2).float().mean()

    # Cutoff tracking
    metrics['cutoffs'] = cutoffs_avg
    metrics['cutoff_ema'] = cutoff_ema
    metrics['cutoff_abs_deviation'] = torch.abs(cutoffs_avg - cutoff_ema).mean()

    # Router activation statistics
    if weights.numel() == 0:
        zero = weights.new_tensor(0.0)
        metrics['activation_weight_mean'] = zero
        metrics['activation_weight_std'] = zero
        metrics['activation_weight_max'] = zero
        metrics['activation_weight_min'] = zero
    else:
        metrics['activation_weight_mean'] = weights.mean()
        if weights.numel() < 2:
            metrics['activation_weight_std'] = weights.new_tensor(0.0)
        else:
            metrics['activation_weight_std'] = weights.std()
        metrics['activation_weight_max'] = weights.max()
        metrics['activation_weight_min'] = weights.min()

    # Router logit statistics (pre-activation)
    metrics['router_logit_mean'] = router_logits_flat.mean()
    metrics['router_logit_std'] = router_logits_flat.std()

    # Representative layer metrics (L1 added for first_layer_dense case)
    repr_layers = {0, 1, n_layer//4, n_layer//2, 3*n_layer//4, n_layer-1}
    first_last_layers = {0, 1, n_layer-1}  # L1 added as "first MoE layer" when L0 is dense

    if layer_idx in repr_layers:
        # E0 cutoff values (all repr layers)
        metrics[f'repr_L{layer_idx}_E0_cutoff'] = cutoffs_avg[0]
        metrics[f'repr_L{layer_idx}_E0_cutoff_ema'] = cutoff_ema[0]
        metrics[f'repr_L{layer_idx}_E0_cutoff_delta'] = torch.abs(cutoffs_avg[0] - cutoff_ema[0])

        # Elast cutoff values (first/last layers only)
        if layer_idx in first_last_layers:
            metrics[f'repr_L{layer_idx}_Elast_cutoff'] = cutoffs_avg[-1]
            metrics[f'repr_L{layer_idx}_Elast_cutoff_ema'] = cutoff_ema[-1]
            metrics[f'repr_L{layer_idx}_Elast_cutoff_delta'] = torch.abs(cutoffs_avg[-1] - cutoff_ema[-1])

        # Per-expert usage at this representative layer
        metrics[f'repr_L{layer_idx}_expert_usage'] = expert_usage

    # Normalization metrics (optional, requires normalizer + indices)
    if normalizer is not None and indices is not None:
        norm_n_tokens = normalizer.shape[0]  # Use different name to avoid shadowing n_tokens parameter

        # 1. norm_selected_ratio: ∑(selected) / ∑(all) — discontinuity measure
        # Compute sum of selected weights per token
        select_norm_sum = torch.zeros(norm_n_tokens, device=normalizer.device, dtype=weights.dtype)
        select_norm_sum.scatter_add_(0, indices, weights)

        # Compute sum of all weights per token (apply activation to all logits)
        if router_activation == "sigmoid":
            all_weights = torch.sigmoid(router_logits_flat)  # (n_tokens, n_experts)
        elif router_activation == "relu":
            import torch.nn.functional as F
            all_weights = F.relu(router_logits_flat)
        elif router_activation == "softmax_k":
            # For softmax_k, all_weights doesn't make semantic sense (softmax is per-expert)
            # Use sigmoid as proxy for "all weights" computation
            all_weights = torch.sigmoid(router_logits_flat)
        else:  # softmax_e or others
            all_weights = torch.sigmoid(router_logits_flat)

        all_norm_sum = all_weights.sum(dim=1)  # (n_tokens,)

        # Ratio: how much of all weight mass is in selected experts
        selected_ratio = select_norm_sum / (all_norm_sum.clamp(min=1e-6))
        metrics['norm_selected_ratio'] = selected_ratio.mean()

        # 2. norm_denominator_mean: Mean normalizer (should ≈ G)
        metrics['norm_denominator_mean'] = normalizer.mean()

        # 3. norm_denominator_std: Std of normalizers
        metrics['norm_denominator_std'] = normalizer.std()

        # 4. zero_weight_ratio: (ReLU only) Fraction with weight=0
        if router_activation == "relu":
            metrics['zero_weight_ratio'] = (weights == 0).float().mean()

        # 5 & 6. Raw sums for eval-time analysis
        metrics['select_norm_sum'] = select_norm_sum.mean()
        metrics['all_norm_sum'] = all_norm_sum.mean()

    # Capacity metrics (optional, requires all three capacity params)
    if above_counts is not None and k_min is not None and k_max is not None:
        n_experts = len(above_counts)
        # Use passed n_tokens if provided (for EP where above_counts is global),
        # otherwise fall back to local router_logits shape
        capacity_n_tokens = n_tokens if n_tokens is not None else router_logits_flat.shape[0]

        # Actual token counts (from expert_usage which is normalized)
        actual_counts = expert_usage * capacity_n_tokens

        # Track capacity bound violations
        hit_max = above_counts > k_max
        hit_min = above_counts < k_min

        metrics['capacity_overflow_rate'] = hit_max.float().mean()
        metrics['capacity_underflow_rate'] = hit_min.float().mean()

        # Raw expert usage without capacity constraints (average across experts)
        raw_usage_tensor = above_counts.float() / capacity_n_tokens
        metrics['capacity_raw_expert_usage'] = raw_usage_tensor.mean()

        # Representative layer E0 raw usage metrics
        if layer_idx in repr_layers:
            # Track what expert 0 would naturally select (without capacity)
            metrics[f'repr_L{layer_idx}_E0_raw_usage'] = above_counts[0].float() / capacity_n_tokens

    # Assert: All outputs are tensors (ModelBase will convert to Python types)
    for k, v in metrics.items():
        assert torch.is_tensor(v), \
            f"compute_routing_metrics() should return tensors, got {type(v)} for '{k}'. " \
            f"ModelBase.forward() is responsible for converting to Python types."

    return metrics
