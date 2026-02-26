"""Mixture of Depth and Experts (MoDE) MLP implementation."""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.models.model_base import BaseMLP, ModelConfig, RouterMixin


class MoDEMLP(BaseMLP, RouterMixin):
    """Mixture of Depth and Experts MLP."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        
        # Ensure required parameters are not None
        assert config.n_experts is not None, "n_experts must be specified for MoDE"
        assert config.expert_dim is not None, "expert_dim must be specified for MoDE"
        
        # Router parameters (one per expert)
        self.router_w = nn.Parameter(
            torch.randn(config.n_embd, config.n_experts) * 0.02
        )
        
        # Expert parameters
        self.weight1 = nn.Parameter(
            torch.randn(config.n_experts, config.expert_dim, config.n_embd) * 0.02
        )
        self.bias1 = nn.Parameter(torch.zeros(config.n_experts, config.expert_dim))
        
        self.weight2 = nn.Parameter(
            torch.randn(config.n_experts, config.n_embd, config.expert_dim) * 0.02
        )
        self.bias2 = nn.Parameter(torch.zeros(config.n_experts, config.n_embd))
        
        self.act = nn.GELU()
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        n_experts = self.router_w.shape[1]
        
        # Compute routing decisions for each expert
        p, g = self.compute_router_scores(x, self.router_w)  # (B, T, n_experts)
        
        # Flatten for efficient processing
        x_flat = x.view(-1, C)  # (B*T, C)
        p_flat = p.view(-1, n_experts)  # (B*T, n_experts)
        g_flat = g.view(-1, n_experts)  # (B*T, n_experts)
        
        # Find which tokens go to each expert
        expert_indices = []
        for e in range(n_experts):
            idx_e = (g_flat[:, e] == 1).nonzero(as_tuple=True)[0]
            expert_indices.append(idx_e)
        
        # Process tokens through experts
        output = torch.zeros_like(x_flat)
        
        for e in range(n_experts):
            if len(expert_indices[e]) == 0:
                continue
            
            # Get tokens for this expert
            x_e = x_flat[expert_indices[e]]  # (n_tokens, C)
            
            # Expert forward pass
            h = F.linear(x_e, self.weight1[e].t(), self.bias1[e])  # (n_tokens, expert_dim)
            h = self.act(h)
            h = F.linear(h, self.weight2[e].t(), self.bias2[e])  # (n_tokens, C)
            
            # Apply soft gate and accumulate
            p_e = p_flat[expert_indices[e], e:e+1]  # (n_tokens, 1)
            output[expert_indices[e]] += h * p_e
        
        # Reshape back
        output = output.view(B, T, C)
        
        # Normalize by number of active experts per token
        active_experts = g.sum(dim=-1, keepdim=True).clamp(min=1.0)
        output = output / active_experts
        
        # Metrics
        metrics = {
            'mode_soft_usage': p.mean(dim=(0, 1)),  # Per-expert usage
            'mode_hard_usage': g.mean(dim=(0, 1)),  # Per-expert usage
            'mode_avg_experts_per_token': active_experts.mean(),
        }
        
        return output, metrics 
