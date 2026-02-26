"""Triton-accelerated Global Expert Choice (GEC) MLP implementation.

Drop-in replacement for GECMLP that uses optimized Triton kernels with autograd support:
- gather(): Replaces x_flat[permutation_indices] with autograd-enabled wrapper
- scatter(): Replaces output.index_add_(0, permutation_indices, h) with fused backward pass
"""

from typing import Dict, Tuple

import torch
import torch.nn as nn

from ..model_base import BaseMLP, ModelConfig, RouterMixin
from src.ops import gather, scatter


class GECTritonMLP(BaseMLP, RouterMixin):
    """Triton-accelerated Global Expert Choice MLP.

    Identical to GECMLP but uses Triton kernels for gather/scatter operations.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        assert config.n_experts is not None, "n_experts must be specified for GEC"
        assert config.expert_dim is not None, "expert_dim must be specified for GEC"

        # Router parameters
        self.router = nn.Linear(config.n_embd, config.n_experts, bias=False)

        # Expert parameters: 2D ParameterList for per-expert optimizer states
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(config.n_experts)
        ])
        self.bias1 = nn.Parameter(torch.zeros(config.n_experts, config.expert_dim))

        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(config.n_experts)
        ])
        self.bias2 = nn.Parameter(torch.zeros(config.n_experts, config.n_embd))

        self.act = nn.GELU()

        self.register_buffer('cutoff_ema', torch.zeros(config.n_experts))
        self.ema_decay = 0.99
        self.density = config.density

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        n_experts = self.config.n_experts

        # Router (identical to GECMLP)
        router_logits = self.router(x)
        x_flat = x.view(-1, C)
        router_logits_flat = router_logits.view(-1, n_experts)
        n_tokens = B * T

        k = int(n_tokens * self.density)
        topk_values, topk_indices = torch.topk(router_logits_flat.t(), k=min(k, n_tokens), dim=1)
        cutoffs = topk_values[:, -1] if k > 0 else torch.zeros(n_experts, device=x.device)

        with torch.no_grad():
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs

        permutation_indices = topk_indices.reshape(-1)

        # TRITON GATHER: Replaces x_flat[permutation_indices]
        x_permuted = gather(
            x_flat,
            permutation_indices,
            num_experts=n_experts,
            capacity=k,
        )  # (n_experts, k, C)

        # Stack 2D parameters to 3D before batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        # Expert computation (identical to GECMLP)
        h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))
        h = h + self.bias1.unsqueeze(1)
        h = self.act(h)
        h = torch.bmm(h, weight2_3d.transpose(1, 2))
        h = h + self.bias2.unsqueeze(1)

        # Apply weights via scatter operation
        weights = torch.sigmoid(topk_values).reshape(-1)  # (n_experts * k,)

        # TRITON SCATTER: Replaces output.index_add_(0, permutation_indices, h)
        output = scatter(
            h,
            permutation_indices,
            n_experts,
            k,
            n_tokens,
            weights,
        )

        # Normalization (identical to GECMLP)
        token_counts = torch.bincount(permutation_indices, minlength=n_tokens).float()
        token_counts = token_counts.clamp(min=1e-6).unsqueeze(-1)
        output = output / token_counts
        output = output.view(B, T, C)

        # Metrics (identical to GECMLP)
        expert_token_counts = torch.full((n_experts,), k, device=x.device)
        avg_experts = token_counts.squeeze(-1).mean()
        metrics = {
            'gec_expert_usage': expert_token_counts / n_tokens,
            'gec_avg_experts_per_token': avg_experts,
            'gec_cutoff_ema': self.cutoff_ema.clone(),
            'gec_cutoffs': cutoffs.clone(),
            'gec_max_experts_per_token': token_counts.squeeze(-1).max(),
            'gec_tokens_with_no_expert': (token_counts.squeeze(-1) == 0).float().sum() / n_tokens,
        }

        return output, metrics