"""Global Expert Choice (GEC) MLP with segmented reduction optimization."""

from typing import Dict, Tuple

import torch
import torch.nn as nn

from ..model_base import BaseMLP, ModelConfig, RouterMixin
from ...utils import compute_routing_metrics


class GECSegmentedMLP(BaseMLP, RouterMixin):
    """Global Expert Choice MLP using sort + segmented reduction instead of scatter_add.

    Replaces atomic scatter_add with a sort-based segmented reduction for massive speedup.
    Maintains exact numerical equivalence to the original GECMLP implementation.

    Key optimization: When multiple experts select the same token, instead of using
    atomic scatter_add operations, we:
    1. Sort contributions by token ID to group same-token contributions together
    2. Use torch.segment_reduce to sum contiguous groups (coalesced, non-atomic)
    3. Write results once per unique token (non-atomic indexed assignment)

    This eliminates atomics entirely and leverages GPU memory bandwidth efficiently.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        # Ensure required parameters are not None
        assert config.n_experts is not None, "n_experts must be specified for GEC"
        assert config.expert_dim is not None, "expert_dim must be specified for GEC"

        # Router parameters (one per expert)
        self.router = nn.Linear(config.n_embd, config.n_experts, bias=False)

        # Expert parameters - 2D ParameterList instead of 3D tensors
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(config.n_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(config.n_experts)
        ])
        self.bias1 = nn.Parameter(torch.zeros(config.n_experts, config.expert_dim))
        self.bias2 = nn.Parameter(torch.zeros(config.n_experts, config.n_embd))

        self.act = nn.GELU()

        # Moving average of cutoff values per expert
        self.register_buffer('cutoff_ema', torch.zeros(config.n_experts))
        self.ema_decay = 0.99  # EMA decay rate

        # Representative layers for detailed metrics tracking
        self.repr_layers = {0, config.n_layer//4, config.n_layer//2, 3*config.n_layer//4, config.n_layer-1}
        self.temporal_window = getattr(config, 'temporal_window', 100)
        self.temporal_warmup = getattr(config, 'temporal_warmup', 10)

        # Temporal buffers for representative layers
        for layer in self.repr_layers:
            self.register_buffer(f'cutoff_history_L{layer}', torch.zeros(self.temporal_window, config.n_experts))
            self.register_buffer(f'history_idx_L{layer}', torch.tensor(0))
            self.register_buffer(f'prev_cutoff_L{layer}', torch.zeros(config.n_experts))

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        n_experts = self.config.n_experts

        # Compute routing scores for all tokens to all experts (einsum)
        router_logits = self.router(x)  # (B, T, n_experts)

        # Flatten for global selection
        x_flat = x.view(-1, C)  # (B*T, C)
        router_logits_flat = router_logits.view(-1, n_experts)  # (B*T, n_experts)
        n_tokens = B * T

        # Always use topk for exact k tokens per expert (compute-matching)
        k = n_tokens // self.config.expansion

        # Select top-k tokens for ALL experts in parallel (on raw logits)
        topk_values, topk_indices = torch.topk(router_logits_flat.t(), k=min(k, n_tokens), dim=1)  # (n_experts, k)

        # Get cutoff values
        cutoffs = topk_values[:, -1] if k > 0 else torch.zeros(n_experts, device=x.device)

        # Update moving averages
        with torch.no_grad():
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs  # type: ignore

        # Create permutation indices
        # Flatten topk_indices to get all selected tokens in order by expert
        permutation_indices = topk_indices.reshape(-1)  # (n_experts * k,)
        M = permutation_indices.shape[0]

        # Permute input tokens
        x_permuted = x_flat[permutation_indices]  # (M, C)

        # Process all experts in parallel
        # Reshape to separate experts: (n_experts, k, C)
        x_permuted = x_permuted.view(n_experts, -1, C)

        # Stack 2D parameters to 3D before batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        # First layer: x -> hidden
        # weight1_3d: (n_experts, expert_dim, C)
        # x_permuted: (n_experts, k, C)
        h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))  # (n_experts, k, expert_dim)
        h = h + self.bias1.unsqueeze(1)  # (n_experts, k, expert_dim)
        h = self.act(h)

        # Second layer: hidden -> output
        # weight2_3d: (n_experts, C, expert_dim)
        # h: (n_experts, k, expert_dim)
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (n_experts, k, C)
        h = h + self.bias2.unsqueeze(1)  # (n_experts, k, C)

        # Apply soft weights from router (activate the selected logits)
        weights = self.apply_router_activation(topk_values, self.config.router_activation).view(n_experts, -1, 1)  # (n_experts, k, 1)

        # Compute normalizer using mixin method
        normalizer = self.compute_normalizer(
            mode=self.config.normalization_mode,
            n_tokens=n_tokens,
            indices=permutation_indices,
            weights=weights.view(-1),
            router_logits_flat=router_logits_flat,
            router_activation=self.config.router_activation,
            device=x.device
        )  # (n_tokens,)

        # Normalize h BEFORE reduction (compile will fuse operations)
        normalizer_h = normalizer[permutation_indices].view(n_experts, -1, 1).to(h.dtype)
        h = h * weights / normalizer_h

        # Flatten contributions: (M, C)
        contributions = h.view(M, C)

        # ========================================================================
        # OPTIMIZED REDUCTION: Replace scatter_add with sort + segmented reduction
        # ========================================================================

        # Step 1: Sort by token_id to group contributions for the same token together
        sorted_indices = torch.argsort(permutation_indices, stable=True)  # (M,)
        sorted_token_ids = permutation_indices[sorted_indices]  # (M,) - sorted token IDs
        sorted_contributions = contributions[sorted_indices]  # (M, C) - reordered contributions

        # Step 2: Find segment lengths for consecutive identical token_ids
        # counts: (U,) number of consecutive occurrences for each unique token
        _, counts = torch.unique_consecutive(sorted_token_ids, return_counts=True)

        # Step 3: Perform segmented sum reduction over contributions
        # Input: sorted_contributions (M, C)
        # Segments: defined by 'counts' (U segments, lengths sum to M)
        # Output: reduced_contributions (U, C) - sum of contributions per unique token
        reduced_contributions = torch.segment_reduce(
            sorted_contributions,
            reduce='sum',
            lengths=counts
        )  # (U, C)

        # Step 4: Extract the unique token IDs corresponding to each segment
        # The first element of each segment in sorted_token_ids is the token ID
        segment_starts = torch.cat([
            torch.tensor([0], device=counts.device),
            torch.cumsum(counts[:-1], dim=0)
        ])
        unique_token_ids = sorted_token_ids[segment_starts]  # (U,) - token IDs for each reduced output

        # Step 5: Initialize full output and assign reduced results
        # output_flat[i] = sum of all contributions for token i (0 if never selected)
        output_flat = torch.zeros(n_tokens, C, device=x.device, dtype=h.dtype)  # (N, C)
        output_flat[unique_token_ids] = reduced_contributions  # Non-atomic, coalesced write

        # Reshape back
        output = output_flat.view(B, T, C)

        # Compute metrics using unified method
        token_fanout = torch.bincount(permutation_indices, minlength=n_tokens).float()
        expert_token_counts = torch.full((n_experts,), k, device=x.device)
        expert_usage = expert_token_counts / n_tokens

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,
            cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
            weights=weights.view(-1),
            router_logits_flat=router_logits_flat,
            token_fanout=token_fanout,
            expert_usage=expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=normalizer,
            indices=permutation_indices,
            normalization_mode=self.config.normalization_mode,
        )

        # Add raw layer data for visualization (during eval only)
        if not self.training:
            metrics['layer_data'] = {
                'weights': weights.view(-1).detach(),  # (M,)
                'fanout': token_fanout.detach(),  # (n_tokens,)
                'cutoffs': cutoffs.detach(),  # (n_experts,)
                'router_logits': router_logits_flat.detach(),  # (n_tokens, n_experts)
            }

        return output, metrics
