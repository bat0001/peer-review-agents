"""GEC_shared with trainable threshold routing (inherits from GECSharedMLP)."""

from typing import Dict, Tuple

import torch
import torch.nn.functional as F
from torch import Tensor

from .shared import GECSharedMLP
from ...utils import compute_routing_metrics


class GECSharedMLPTrainableThreshold(GECSharedMLP):
    """GEC_shared with threshold routing that supports training mode.

    Extends GECSharedMLP with training-compatible threshold routing:
    - Training mode: Dual-path (top-k for EMA + threshold for routing)
    - Eval mode: Threshold only (same as inference)

    Backward compatible with parent GECSharedMLP for top-k routing.
    """

    def __init__(self, config):
        super().__init__(config)
        # Override cutoff_ema initialization: use very negative value
        # so that in threshold mode, experts can actually activate initially
        self.cutoff_ema.fill_(-10.0)

    def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Dispatcher: calls topk or threshold forward based on routing mode.

        Routing mode selection:
        - None (default): auto-switch based on self.training (topk in train, threshold in eval)
        - 'topk': always use topk routing (perfect load balance, differentiable)
        - 'threshold': always use threshold routing (causal, dynamic)
        """
        # Determine effective routing mode
        if self.routing_mode is None:
            # Auto mode: topk for training, threshold for eval
            mode = 'topk' if self.training else 'threshold'
        else:
            # Explicit override
            mode = self.routing_mode

        if mode == 'topk':
            # Call parent's forward_topk (standard top-k routing)
            return super().forward_topk(x, layer_idx)
        else:  # mode == 'threshold'
            # Call our override (supports training)
            return self.forward_threshold(x, layer_idx)

    def forward_threshold(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Threshold routing supporting both training and inference.

        Training mode (dual mode):
          1. Top-k (no_grad) to extract cutoffs for EMA updates
          2. Threshold routing (with gradients) for actual computation

        Eval mode:
          - Threshold routing only (no top-k overhead)
        """
        B, T, C = x.shape
        n_routed_experts = self.n_routed_experts
        n_tokens = B * T

        # Flatten
        x_flat = x.view(-1, C)  # (B*T, C)

        # === TRAINING: Parallel top-k for EMA ===
        if self.training:
            # Compute router logits
            router_logits = self.router(x)  # (B, T, n_routed_experts)
            router_logits_flat = router_logits.view(-1, n_routed_experts)  # (B*T, n_routed_experts)

            with torch.no_grad():
                # Compute k using GEC_shared formula
                G = self.config.granularity
                E = self.config.expansion
                k = int(n_tokens * (G - 1) // (G * E))

                topk_values, _ = torch.topk(
                    router_logits_flat.t(), k=min(k, n_tokens), dim=1
                )
                cutoffs = topk_values[:, -1]  # (n_routed_experts,)

                # Update EMA
                self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
                self.cutoff_ema_count += 1
        else:
            # Compute router logits (needed for threshold routing)
            router_logits = self.router(x)
            router_logits_flat = router_logits.view(-1, n_routed_experts)

        # === THRESHOLD ROUTING (supports autograd) ===
        # Only fanout normalization mode is optimized
        if self.config.normalization_mode != 'fanout':
            raise NotImplementedError(
                f"Threshold routing only supports normalization_mode='fanout', got '{self.config.normalization_mode}'"
            )

        # Shared expert (always active for all tokens)
        shared_output = self._shared_expert_forward(x_flat)  # (B*T, C)

        # Loop 1: Compute normalizer incrementally
        normalizer = torch.zeros(n_tokens, device=x.device, dtype=torch.float32)

        for expert_idx in range(n_routed_experts):
            # Use >= so that when logits and cutoff are both ~0, experts can activate
            mask = router_logits_flat[:, expert_idx] >= self.cutoff_ema[expert_idx]
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            normalizer.index_add_(0, active_indices, weights.float())

        # Add shared expert contribution
        normalizer = normalizer + 1.0

        # Normalize shared output once
        shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)

        # Loop 2: Process experts and accumulate directly (NO intermediate buffers!)
        token_fanout = torch.zeros(n_tokens, device=x.device)
        has_active_experts = False

        for expert_idx in range(n_routed_experts):
            mask = router_logits_flat[:, expert_idx] >= self.cutoff_ema[expert_idx]
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            has_active_experts = True

            # Process tokens (gradients flow here in training)
            x_active = x_flat[active_indices]
            h = self._expert_forward(x_active, expert_idx)

            # Router activation
            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            # Normalize by per-token normalizer
            normalizer_h = normalizer[active_indices].unsqueeze(-1).to(h.dtype)
            h_weighted = h * weights.unsqueeze(-1) / normalizer_h

            # Add directly into shared_output (no intermediate buffer!)
            shared_output.index_add_(0, active_indices, h_weighted.to(shared_output.dtype))

            # Track token fanout for metrics
            ones = torch.ones(len(active_indices), device=x.device)
            token_fanout.scatter_add_(0, active_indices, ones)

        output = shared_output

        # Reshape back
        output = output.view(B, T, C)

        # Include shared expert in fanout (token_fanout already computed in Loop 2)
        token_fanout_with_shared = token_fanout + 1.0

        # Compute expert token counts
        expert_token_counts = torch.zeros(n_routed_experts, device=x.device)
        for e in range(n_routed_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e >= self.cutoff_ema[e]).float().sum()

        # Expert usage includes shared (1.0) + routed
        total_expert_usage = torch.cat([
            torch.ones(1, device=x.device),  # Shared expert processes all tokens
            expert_token_counts / n_tokens    # Routed experts
        ])

        # Simplified metrics (no intermediate tensors needed)
        metrics = {
            'gec_shared_expert_usage': total_expert_usage,
            'gec_shared_avg_experts_per_token': token_fanout_with_shared.mean(),
            'gec_shared_cutoff_ema': self.cutoff_ema.clone(),
            'gec_shared_max_experts_per_token': token_fanout_with_shared.max(),
            'gec_shared_min_experts_per_token': token_fanout_with_shared.min(),
        }

        # Add raw layer data for visualization (during eval only)
        if not torch.is_grad_enabled():
            weights_viz = self.apply_router_activation(router_logits_flat, self.config.router_activation)
            metrics['layer_data'] = {
                'weights': weights_viz.view(-1).detach(),
                'fanout': token_fanout_with_shared.detach(),
                'cutoffs': self.cutoff_ema.clone().detach(),
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics
