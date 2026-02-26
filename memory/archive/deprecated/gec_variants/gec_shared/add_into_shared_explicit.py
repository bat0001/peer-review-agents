"""AddIntoShared variant with explicit dtype casting.

Memory optimization: Instead of creating separate routed_output buffer and adding it to
shared_output, we directly index_add into the shared_output buffer to reduce memory usage.

Dtype handling: Uses explicit intermediate variables for all dtype conversions, making
the casting strategy visible and potentially affecting torch.compile optimization.
"""

from typing import Dict, Tuple

import torch
import torch.nn.functional as F

from .shared import GECSharedMLP
from ...utils import compute_routing_metrics


class AddIntoSharedExplicitGECMLP(GECSharedMLP):
    """GEC Shared MLP with memory-optimized forward pass and explicit dtype casting.

    Optimization: Reuses shared_output buffer for accumulation instead of creating
    a separate routed_output buffer, saving B*T*C memory.

    Dtype handling: All dtype conversions use explicit intermediate variables for clarity
    and to test impact on torch.compile optimization.
    """

    def forward_topk(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with global top-k routing (memory-optimized with explicit dtype casts)."""
        B, T, C = x.shape
        n_routed_experts = self.n_routed_experts

        # Process shared expert (all tokens)
        x_flat = x.view(-1, C)  # (B*T, C)

        # Shared expert forward pass
        shared_h = F.linear(x_flat, self.shared_weight1)  # (B*T, expert_dim)
        shared_h = F.relu(shared_h).square()
        shared_output = F.linear(shared_h, self.shared_weight2)  # (B*T, C)

        # Compute routing scores for all tokens to all routed experts
        router_logits = self.router(x)  # (B, T, n_routed_experts)

        # Flatten for global selection
        router_logits_flat = router_logits.view(-1, n_routed_experts)  # (B*T, n_routed_experts)
        n_tokens = B * T

        # Use topk for exact k tokens per expert (compute-matching)
        G = self.config.granularity
        E = self.config.expansion
        k = int(n_tokens * (G - 1) // (G * E))

        # Select top-k tokens for ALL routed experts in parallel (on raw logits)
        topk_values, topk_indices = torch.topk(router_logits_flat.t(), k=min(k, n_tokens), dim=1)  # (n_routed_experts, k)

        # Get cutoff values (last selected token's probability for each expert)
        cutoffs = topk_values[:, -1]  # (n_routed_experts,)

        # Update moving averages (for metrics only)
        with torch.no_grad():
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
            self.cutoff_ema_count += 1

        # Process routed experts
        # Create permutation indices
        permutation_indices = topk_indices.reshape(-1)  # (n_routed_experts * k,)

        # Permute input tokens
        x_permuted = x_flat[permutation_indices]  # (n_routed_experts * k, C)

        # Reshape to separate experts: (n_routed_experts, k, C)
        x_permuted = x_permuted.view(n_routed_experts, k, C)

        # Stack 2D parameters to 3D before batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        # First layer: x -> hidden
        h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))  # (n_routed_experts, k, expert_dim)
        h = F.relu(h).square()

        # Second layer: hidden -> output
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (n_routed_experts, k, C)

        # Apply soft weights from router (activate the selected logits)
        weights = self.apply_router_activation(topk_values, self.config.router_activation).view(n_routed_experts, k, 1)  # (n_routed_experts, k, 1)

        # Compute normalizer using mixin method (baseline=0.0 for routed experts only)
        normalizer = self.compute_normalizer(
            mode=self.config.normalization_mode,
            n_tokens=n_tokens,
            indices=permutation_indices,
            weights=weights.view(-1),
            router_logits_flat=router_logits_flat,
            router_activation=self.config.router_activation,
            device=x.device,
            baseline=0.0
        )  # (n_tokens,)

        # Add 1.0 for shared expert (always active with implicit weight=1.0)
        normalizer = normalizer + 1.0

        # Normalize h BEFORE scatter (compile will fuse with scatter)
        normalizer_h = normalizer[permutation_indices].view(n_routed_experts, k, 1)
        # EXPLICIT CAST: Cast division result to h's dtype
        h = h * (weights / normalizer_h).to(h.dtype)

        # Flatten back
        h = h.view(-1, C)  # (n_routed_experts * k, C)

        # OPTIMIZATION: Normalize shared expert output first, then accumulate routed outputs directly
        # This reuses the shared_output buffer instead of creating a separate routed_output buffer
        # EXPLICIT CAST: Use intermediate variable for normalizer casting
        normalizer_cast = normalizer.unsqueeze(-1).to(shared_output.dtype)
        shared_output = shared_output / normalizer_cast

        # Accumulate routed outputs directly into shared_output (saves B*T*C memory)
        # EXPLICIT CAST: Use intermediate variable for h casting
        h_cast = h.to(shared_output.dtype)
        shared_output.index_add_(0, permutation_indices, h_cast)

        # Output is already combined in shared_output
        output = shared_output

        # Reshape back
        output = output.view(B, T, C)

        # Compute metrics using unified method
        token_fanout = torch.zeros(n_tokens, device=x.device)
        ones = torch.ones(len(permutation_indices), device=x.device)
        token_fanout.scatter_add_(0, permutation_indices, ones)

        # All routed experts process exactly k tokens
        expert_token_counts = torch.full((n_routed_experts,), k, device=x.device)

        # For GEC_shared: expert_usage includes shared expert (1.0) + routed experts
        total_expert_usage = torch.cat([
            torch.ones(1, device=x.device),  # Shared expert processes all tokens
            expert_token_counts / n_tokens    # Routed experts
        ])

        # Adjust token_fanout to include shared expert (always active)
        token_fanout_with_shared = token_fanout + 1.0  # Every token has shared expert

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,
            cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
            weights=weights.view(-1),
            router_logits_flat=router_logits_flat,
            token_fanout=token_fanout_with_shared,
            expert_usage=total_expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=normalizer,
            indices=permutation_indices,
            normalization_mode=self.config.normalization_mode,
        )

        # Add raw layer data for visualization (during eval only)
        if not torch.is_grad_enabled():
            metrics['layer_data'] = {
                'weights': weights.view(-1).detach(),
                'fanout': token_fanout_with_shared.detach(),
                'cutoffs': cutoffs.detach(),
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics
