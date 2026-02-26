"""GEC with trainable threshold routing (inherits from GECMLP)."""

from typing import Dict, Tuple

import torch
import torch.nn.functional as F
from torch import Tensor

from .gec import GECMLP
from ...utils import compute_routing_metrics


class GECMLPTrainableThreshold(GECMLP):
    """GEC with threshold routing that supports training mode.

    Extends GECMLP with training-compatible threshold routing:
    - Training mode: Dual-path (top-k for EMA + threshold for routing)
    - Eval mode: Threshold only (same as inference)

    Backward compatible with parent GECMLP for top-k routing.
    """

    def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Dispatcher: calls topk or threshold forward based on routing mode.

        Routing mode selection:
        - None (default): auto-switch based on self.training (topk in train, threshold in eval)
        - 'topk': always use topk routing (perfect load balance, differentiable)
        - 'threshold': always use threshold routing (causal, dynamic)
        """
        # Determine effective routing mode
        if self.config.routing_mode is None:
            # Auto mode: topk for training, threshold for eval
            mode = 'topk' if self.training else 'threshold'
        else:
            # Explicit override
            mode = self.config.routing_mode

        if mode == 'topk':
            # Call parent's forward (which does top-k routing)
            return super().forward(x, layer_idx)
        else:  # mode == 'threshold'
            # Call our threshold implementation (supports training)
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
        n_experts = self.config.n_experts

        # Compute router logits
        router_logits = self.router(x)  # (B, T, n_experts)
        router_logits_flat = router_logits.view(-1, n_experts)  # (B*T, n_experts)
        n_tokens = B * T
        x_flat = x.view(-1, C)

        # === TRAINING: Parallel top-k for EMA ===
        if self.training:
            with torch.no_grad():
                k = n_tokens // self.config.expansion
                topk_values, _ = torch.topk(
                    router_logits_flat.t(), k=min(k, n_tokens), dim=1
                )
                cutoffs = topk_values[:, -1] if k > 0 else torch.zeros(n_experts, device=x.device)

                # Update EMA
                self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs

        # === THRESHOLD ROUTING (supports autograd) ===
        all_active_indices = []
        all_weights = []
        all_expert_outputs = []

        for expert_idx in range(n_experts):
            # Threshold check (differentiable in training!)
            mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            # Process active tokens (gradients flow here in training)
            x_active = x_flat[active_indices]

            # Expert forward pass (nanochat style: no bias, ReLU²)
            h = torch.bmm(
                x_active.unsqueeze(0),
                self.expert_weight1[expert_idx].unsqueeze(0).transpose(1, 2)
            ).squeeze(0)  # (n_active, expert_dim)
            h = F.relu(h).square()  # ReLU² (nanochat style)
            h = torch.bmm(
                h.unsqueeze(0),
                self.expert_weight2[expert_idx].unsqueeze(0).transpose(1, 2)
            ).squeeze(0)  # (n_active, C)

            # Router activation
            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            all_active_indices.append(active_indices)
            all_weights.append(weights)
            all_expert_outputs.append(h)

        # Combine outputs
        if len(all_active_indices) > 0:
            permutation_indices = torch.cat(all_active_indices)
            weights = torch.cat(all_weights)
            expert_outputs = torch.cat(all_expert_outputs)

            # Compute normalizer
            normalizer = self.compute_normalizer(
                mode=self.config.normalization_mode,
                n_tokens=n_tokens,
                indices=permutation_indices,
                weights=weights,
                router_logits_flat=router_logits_flat,
                router_activation=self.config.router_activation,
                device=x.device
            )

            # Normalize and scatter
            normalizer_h = normalizer[permutation_indices].unsqueeze(-1).to(expert_outputs.dtype)
            h_weighted = expert_outputs * weights.unsqueeze(-1) / normalizer_h

            output = torch.zeros_like(x_flat)
            output.index_add_(0, permutation_indices, h_weighted.to(output.dtype))
        else:
            output = torch.zeros_like(x_flat)
            permutation_indices = torch.tensor([], dtype=torch.long, device=x.device)
            normalizer = torch.ones(n_tokens, device=x.device)

        output = output.view(B, T, C)

        # Compute metrics
        token_fanout = torch.bincount(permutation_indices, minlength=n_tokens).float()

        # Expert token counts
        expert_token_counts = torch.zeros(n_experts, device=x.device)
        for e in range(n_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e > self.cutoff_ema[e]).float().sum()

        expert_usage = expert_token_counts / n_tokens

        # Only compute full metrics if we have activated experts
        if len(all_weights) > 0:
            metrics = compute_routing_metrics(
                cutoffs=self.cutoff_ema.clone(),  # Use EMA as current cutoffs
                cutoff_ema=self.cutoff_ema.clone(),
                weights=weights,
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
        else:
            # No experts activated - simplified metrics
            metrics = {
                'gec_expert_usage': expert_usage,
                'gec_avg_experts_per_token': token_fanout.mean(),
                'gec_cutoff_ema': self.cutoff_ema.clone(),
            }

        # Add raw layer data for visualization (during eval only)
        if not self.training:
            metrics['layer_data'] = {
                'weights': weights.view(-1).detach() if len(all_weights) > 0 else torch.tensor([]),
                'fanout': token_fanout.detach(),
                'cutoffs': self.cutoff_ema.clone().detach(),
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics
