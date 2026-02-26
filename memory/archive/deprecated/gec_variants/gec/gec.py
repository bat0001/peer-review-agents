"""Global Expert Choice (GEC) MLP implementation."""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..model_base import BaseMLP, ModelConfig, RouterMixin
from ...utils import compute_routing_metrics


class GECMLP(BaseMLP, RouterMixin):
    """Global Expert Choice MLP where experts select top-k tokens.

    Memory usage scales as O(n_experts * selection_rate * batch_size * seq_length).
    For example, with 4 experts and selection_rate=0.25, we process the same number
    of token-expert pairs as there are input tokens. With 8 experts and
    selection_rate=0.5, we process 4x as many token-expert pairs as input tokens.

    Key differences from standard MoE:
    - Experts select tokens (not tokens selecting experts)
    - Each expert processes exactly k = n_tokens * selection_rate tokens
    - Tokens can be selected by multiple experts (soft assignment)
    - Uses scatter_add for proper accumulation when tokens overlap
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        # Ensure required parameters are not None
        assert config.n_experts is not None, "n_experts must be specified for GEC"
        assert config.expert_dim is not None, "expert_dim must be specified for GEC"

        # Router layer (one per expert) - no bias! (nanochat style)
        self.router = nn.Linear(config.n_embd, config.n_experts, bias=False)

        # Expert parameters - ParameterList of 2D tensors for per-expert optimizer states
        # Use torch.empty() since init_weights() will initialize them properly
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(config.n_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(config.n_experts)
        ])

        # No separate activation module - use ReLU² inline (nanochat style)

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

        # Compute routing scores for all tokens to all experts
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
        
        # Permute input tokens
        x_permuted = x_flat[permutation_indices]  # (n_experts * k, C)
        
        # Process all experts in parallel
        # Reshape to separate experts: (n_experts, k, C)
        x_permuted = x_permuted.view(n_experts, -1, C)

        # Stack 2D parameters to 3D for batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])  # (n_experts, expert_dim, C)
        weight2_3d = torch.stack([w for w in self.expert_weight2])  # (n_experts, C, expert_dim)

        # First layer: x -> hidden (nanochat style: no bias, ReLU²)
        # weight1_3d: (n_experts, expert_dim, C)
        # x_permuted: (n_experts, k, C)
        h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))  # (n_experts, k, expert_dim)
        h = F.relu(h).square()  # ReLU² (nanochat style)

        # Second layer: hidden -> output (nanochat style: no bias)
        # weight2_3d: (n_experts, C, expert_dim)
        # h: (n_experts, k, expert_dim)
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (n_experts, k, C)
        
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

        # Normalize h BEFORE scatter (compile will fuse with scatter)
        normalizer_h = normalizer[permutation_indices].view(n_experts, -1, 1).to(h.dtype)
        h = h * weights / normalizer_h

        # Flatten back
        h = h.view(-1, C)  # (n_experts * k, C)

        # Scatter
        output = torch.zeros_like(x_flat)
        output.index_add_(0, permutation_indices, h)

        # Reshape back
        output = output.view(B, T, C)

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
                'weights': weights.view(-1).detach(),  # (n_experts * k,)
                'fanout': token_fanout.detach(),  # (n_tokens,)
                'cutoffs': cutoffs.detach(),  # (n_experts,)
                'router_logits': router_logits_flat.detach(),  # (n_tokens, n_experts)
            }

        return output, metrics 
