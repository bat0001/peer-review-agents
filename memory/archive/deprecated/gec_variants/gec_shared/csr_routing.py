"""GEC Shared MLP with CSR-based token-parallel scatter.

This variant uses CSR (Compressed Sparse Row) infrastructure for token-parallel
scatter operations instead of PyTorch's index_add_. The key difference:

- Parent class: Uses index_add_ (slot-parallel internally in PyTorch)
- This class: Uses custom Triton kernel with token-level parallelism

Both approaches are numerically equivalent (when max_experts >= n_routed_experts)
but may have different performance characteristics depending on the specific
hardware and routing pattern.
"""

from __future__ import annotations

from typing import Dict, Tuple

import torch
import torch.nn.functional as F

from src.models.gec_shared.shared import GECSharedMLP
from src.ops.csr import csr_gather, csr_scatter_sum
from src.utils.routing_metrics import compute_routing_metrics


class GECSharedMLPCSR(GECSharedMLP):
    """GEC with Shared Expert using CSR-based token-parallel scatter.

    Inherits from GECSharedMLP and overrides only the forward_topk method to use
    CSR-based scatter operations. All other functionality (initialization, threshold
    routing, metrics, etc.) is inherited from the parent class.

    The CSR approach provides correct gradient flow through router weights via
    the CSRScatterOp.backward operation, similar to the parent but using a
    different kernel implementation.
    """

    def forward_topk(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with global top-k routing using CSR ops.

        Args:
            x: Input tensor (B, T, C)
            layer_idx: Layer index for metrics tracking

        Returns:
            Tuple of:
            - output: Processed output (B, T, C)
            - metrics: Dictionary of routing metrics
        """
        B, T, C = x.shape
        n_routed_experts = self.n_routed_experts
        n_tokens = B * T

        # Flatten
        x_flat = x.view(-1, C)  # (B*T, C)

        # Shared expert (always active for all tokens)
        shared_h = F.linear(x_flat, self.shared_weight1)
        shared_h = F.relu(shared_h).square()
        shared_output = F.linear(shared_h, self.shared_weight2)  # (B*T, C)

        # Compute routing scores for routed experts
        router_logits = self.router(x)  # (B, T, n_routed_experts)
        router_logits_flat = router_logits.view(-1, n_routed_experts)  # (B*T, n_routed_experts)

        # Compute k (capacity per expert) using GEC formula
        G = self.config.granularity
        E = self.config.expansion
        k = int(n_tokens * (G - 1) // (G * E))
        k = max(0, min(k, n_tokens))  # Safety clamp

        # Select top-k tokens for each expert (transpose to get expert-major)
        topk_values, topk_indices = torch.topk(
            router_logits_flat.t(), k=k, dim=1
        )  # (n_routed_experts, k)

        # Get cutoff values (last selected token for each expert)
        cutoffs = topk_values[:, -1] if k > 0 else torch.zeros(
            n_routed_experts, device=x.device, dtype=router_logits.dtype
        )

        # Update moving averages (for threshold routing)
        with torch.no_grad():
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
            self.cutoff_ema_count += 1

        # Determine max_experts (max contributors per token for kernel)
        # Default to n_routed_experts (supports full fan-in)
        # Can be overridden via config.moe_max_fanout for tuning
        max_fanout = getattr(self.config, 'moe_max_fanout', n_routed_experts)

        # Gather tokens for experts using CSR op: (n_routed_experts, k, C)
        x_gathered = csr_gather(x_flat, topk_indices, max_experts=max_fanout)

        # Stack 2D parameters to 3D for batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])  # (E, D_hidden, C)
        weight2_3d = torch.stack([w for w in self.expert_weight2])  # (E, C, D_hidden)

        # Expert MLP computation
        # First layer: x -> hidden (nanochat style: no bias, ReLU²)
        h = torch.bmm(x_gathered, weight1_3d.transpose(1, 2))  # (E, k, D_hidden)
        h = F.relu(h).square()

        # Second layer: hidden -> output (nanochat style: no bias)
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (E, k, C)

        # Apply router activation to get per-slot weights
        slot_weights = self.apply_router_activation(
            topk_values, self.config.router_activation
        )  # (E, k)

        # Compute token-level normalizer (same as parent class)
        permutation_indices = topk_indices.reshape(-1)  # (E*k,)
        normalizer = self.compute_normalizer(
            mode=self.config.normalization_mode,
            n_tokens=n_tokens,
            indices=permutation_indices,
            weights=slot_weights.reshape(-1),
            router_logits_flat=router_logits_flat,
            router_activation=self.config.router_activation,
            device=x.device,
            baseline=0.0
        )  # (n_tokens,)

        # Add 1.0 for shared expert (always active)
        normalizer = normalizer + 1.0

        # Build per-slot normalized weights for CSR scatter
        # For each slot (e, s), weight = slot_weights[e, s] / normalizer[token_id[e, s]]
        token_norm_for_slots = normalizer[topk_indices]  # (E, k)
        slot_weights_normed = slot_weights / token_norm_for_slots  # (E, k)
        weights_flat = slot_weights_normed.reshape(-1).contiguous()  # (E*k,)

        # Flatten expert outputs for CSR scatter: (E*k, C)
        h_flat = h.reshape(-1, C).contiguous()

        # Scatter routed output using CSR kernel
        routed_output = csr_scatter_sum(
            h_flat, topk_indices,
            num_tokens=n_tokens,
            max_experts=max_fanout,
            weights_flat=weights_flat,
            add_into=False
        )  # (B*T, C)

        # Normalize shared expert output by the same normalizer
        shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)

        # Combine shared and routed outputs (both pre-normalized)
        output = shared_output + routed_output
        output = output.view(B, T, C)

        # Compute metrics (same as parent class)
        token_fanout = torch.zeros(n_tokens, device=x.device)
        ones = torch.ones(len(permutation_indices), device=x.device)
        token_fanout.scatter_add_(0, permutation_indices, ones)

        # All routed experts process exactly k tokens
        expert_token_counts = torch.full((n_routed_experts,), k, device=x.device)

        total_expert_usage = torch.cat([
            torch.ones(1, device=x.device),  # Shared expert
            expert_token_counts / n_tokens   # Routed experts
        ])

        token_fanout_with_shared = token_fanout + 1.0

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,
            cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
            weights=slot_weights.reshape(-1),
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
                'weights': slot_weights.reshape(-1).detach(),
                'fanout': token_fanout_with_shared.detach(),
                'cutoffs': cutoffs.detach(),
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics


__all__ = ['GECSharedMLPCSR']
