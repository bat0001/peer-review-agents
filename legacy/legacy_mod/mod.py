"""Mixture of Depth (MoD) MLP implementation."""

from typing import Dict, Tuple

import torch
import torch.nn as nn

from src.models.model_base import BaseMLP, ModelConfig, RouterMixin


class MoDMLP(BaseMLP, RouterMixin):
    """Mixture of Depth MLP - can skip the entire MLP layer."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        
        # Standard MLP layers
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd, bias=True)
        self.gelu = nn.GELU()
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd, bias=True)
        
        # Router parameters
        self.router_w = nn.Parameter(torch.randn(config.n_embd) * 0.02)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        
        # Compute routing decisions
        p, g = self.compute_router_scores(x, self.router_w)
        
        # Apply MLP only to tokens that pass the gate
        if g.any():
            # Mask input
            x_masked = x * g.unsqueeze(-1)
            
            # Standard MLP forward
            h = self.c_fc(x_masked)
            h = self.gelu(h)
            h = self.c_proj(h)
            
            # Apply soft gate for gradient flow
            out = h * p.unsqueeze(-1)
        else:
            out = torch.zeros_like(x)
        
        # Metrics
        metrics = {
            'mod_soft_usage': p.mean(),
            'mod_hard_usage': g.mean(),
        }
        
        return out, metrics 
