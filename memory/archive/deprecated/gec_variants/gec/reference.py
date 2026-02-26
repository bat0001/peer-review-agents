"""Global Expert Choice (GEC) MLP implementation."""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..model_base import BaseMLP, ModelConfig, RouterMixin


class GECMLPReference(BaseMLP, RouterMixin):
    """Reference implementation of Global Expert Choice (GEC) MLP.
    
    This is the original, well-tested implementation used for validation.
    Any modifications to the main GECMLP should be validated against this.
    
    Memory usage scales as O(n_experts * density * batch_size * seq_length).
    For example, with 4 experts and density=0.25, we process the same number
    of token-expert pairs as there are input tokens. With 8 experts and 
    density=0.5, we process 4x as many token-expert pairs as input tokens.
    
    Key differences from standard MoE:
    - Experts select tokens (not tokens selecting experts)
    - Each expert processes exactly k = n_tokens * density tokens
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
        
        # Expert parameters - 2D ParameterList for per-expert optimizer states
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
        
        # Moving average of cutoff values per expert
        self.register_buffer('cutoff_ema', torch.zeros(config.n_experts))
        self.ema_decay = 0.99  # EMA decay rate
        
        # Density from config (fraction of tokens each expert selects)
        self.density = config.density

    def _expert_forward(self, x: torch.Tensor, expert_idx: int) -> torch.Tensor:
        """Forward pass for a single expert."""
        # First layer: x -> hidden
        h = F.linear(x, self.expert_weight1[expert_idx], self.bias1[expert_idx])
        h = self.act(h)
        # Second layer: hidden -> output
        h = F.linear(h, self.expert_weight2[expert_idx], self.bias2[expert_idx])
        return h

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Dispatcher: calls topk or threshold forward based on training mode."""
        if self.training:
            return self.forward_topk(x)
        else:
            return self.forward_threshold(x)

    def forward_topk(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with global top-k routing (perfect load balance)."""
        B, T, C = x.shape
        n_experts = self.config.n_experts
        
        # Compute routing scores for all tokens to all experts
        router_logits = self.router(x)  # (B, T, n_experts)
        
        # Flatten for global selection
        x_flat = x.view(-1, C)  # (B*T, C)
        router_logits_flat = router_logits.view(-1, n_experts)  # (B*T, n_experts)
        n_tokens = B * T
        
        # Always use topk for exact k tokens per expert
        k = int(n_tokens * self.density)
        
        # Select top-k tokens for ALL experts in parallel (on logits)
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
        
        # Apply soft weights from router using selected logits only
        weights = torch.sigmoid(topk_values).view(n_experts, -1, 1)  # (n_experts, k, 1)
        h = h * weights
        
        # Flatten back
        h = h.view(-1, C)  # (n_experts * k, C)
        
        # Initialize output and properly accumulate results
        output = torch.zeros_like(x_flat)
        # Use scatter_add to accumulate outputs from multiple experts
        output.scatter_add_(0, permutation_indices.unsqueeze(-1).expand(-1, C), h)
        
        # Count how many experts processed each token (with scatter_add)
        token_counts = torch.zeros(n_tokens, device=x.device)
        ones = torch.ones(len(permutation_indices), device=x.device)
        token_counts.scatter_add_(0, permutation_indices, ones)
        
        # Normalize by number of experts that processed each token
        # Avoid division by zero for tokens not selected by any expert
        token_counts = token_counts.clamp(min=1e-6).unsqueeze(-1)
        output = output / token_counts
        
        # Reshape back
        output = output.view(B, T, C)
        
        # Compute metrics
        # Count how many tokens each expert processed
        expert_token_counts = torch.zeros(n_experts, device=x.device)
        for e in range(n_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e > cutoffs[e]).float().sum()
        
        # Compute actual average experts per token from the counts
        avg_experts = token_counts.squeeze(-1).mean()
        
        metrics = {
            'gec_expert_usage': expert_token_counts / n_tokens,  # Fraction of tokens per expert
            'gec_avg_experts_per_token': avg_experts,
            'gec_cutoff_ema': self.cutoff_ema.clone(),  # type: ignore  # Current EMA values
            'gec_cutoffs': cutoffs.clone(),  # Current cutoffs
            'gec_max_experts_per_token': token_counts.squeeze(-1).max(),  # Max overlap
            'gec_tokens_with_no_expert': (token_counts.squeeze(-1) == 0).float().sum() / n_tokens,  # Fraction unprocessed
        }
        
        return output, metrics

    def forward_threshold(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with learned threshold routing (causal, for autoregressive generation).

        WARNING: No backward pass support. Use forward_topk() for training.
        """
        assert not torch.is_grad_enabled(), \
            "Threshold routing does not support backward pass. Use forward_topk() for training."

        B, T, C = x.shape
        n_experts = self.config.n_experts
        n_tokens = B * T

        # Compute routing scores for all tokens to all experts
        router_logits = self.router(x)  # (B, T, n_experts)

        # Flatten
        x_flat = x.view(-1, C)  # (B*T, C)
        router_logits_flat = router_logits.view(-1, n_experts)  # (B*T, n_experts)

        # Initialize output and counts
        output = torch.zeros_like(x_flat)
        counts = torch.zeros(n_tokens, device=x.device)

        # Loop through experts (causal - no future tokens needed)
        for expert_idx in range(n_experts):
            # Which tokens activate this expert? (threshold-based)
            mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]  # type: ignore
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            # Process only active tokens with this expert
            x_active = x_flat[active_indices]
            h = self._expert_forward(x_active, expert_idx)

            # Apply sigmoid weights
            weights = torch.sigmoid(router_logits_flat[active_indices, expert_idx])

            # Accumulate
            output.index_add_(0, active_indices, h * weights.unsqueeze(-1))
            counts.index_add_(0, active_indices, torch.ones_like(active_indices, dtype=torch.float))

        # Normalize by number of experts that processed each token
        counts = counts.clamp(min=1e-6).unsqueeze(-1)
        output = output / counts

        # Reshape back
        output = output.view(B, T, C)

        # Compute metrics (similar to training)
        avg_experts = counts.squeeze(-1).mean()
        expert_token_counts = torch.zeros(n_experts, device=x.device)
        for e in range(n_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e > self.cutoff_ema[e]).float().sum()  # type: ignore

        metrics = {
            'gec_expert_usage': expert_token_counts / n_tokens,
            'gec_avg_experts_per_token': avg_experts,
            'gec_cutoff_ema': self.cutoff_ema.clone(),  # type: ignore
            'gec_max_experts_per_token': counts.squeeze(-1).max(),
            'gec_tokens_with_no_expert': (counts.squeeze(-1) == 0).float().sum() / n_tokens,
        }

        return output, metrics
