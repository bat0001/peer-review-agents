"""
Global Expert Choice engine following scattermoe's implementation, i.e. directly scatter into the block gemm then scatter back directly. 
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from typing import Tuple, Dict, Optional

from ..model_base import RouterMixin
from ..engines.index_add import ExpertEngine


class ParallelExperts(nn.Module):
    def __init__(self, n_routed_experts, input_size, output_size) -> None:
        super().__init__()
        # scattermoe needs contiguous weights for the scatter kernel
        self.weight = nn.Parameter(torch.empty(n_routed_experts, output_size, input_size))
        assert False, "Optimizer init for 3D weights is not supported yet"
        self.n_routed_experts = n_routed_experts
        self.input_size = input_size
        self.output_size = output_size
    
    def forward(
        self, 
        inputs: Tensor,
        k: int,
        sorted_expert_idxs: Tensor,
        sorted_scattered_idxs: Tensor,
        expert_offsets: Tensor,
        gates: Optional[Tensor] = None,
        grouped_in: bool = False,
        grouped_out: bool = False
    ) -> Tensor:


class ExpertEngineScatter(ExpertEngine):
    """
    Global Expert Choice engine following scattermoe's implementation, i.e. directly scatter into the block gemm then scatter back directly. 
    """
    def __init__(self, config, n_routed_experts: int):
        super().super().__init__()
        self.config = config
        self.n_routed_experts = n_routed_experts

        # Router: maps tokens to expert logits
        self.router = nn.Linear(config.n_embd, n_routed_experts, bias=False)

        # Expert weights (2-layer MLP, nanochat style: no bias, ReLU²)
        expert_dim = config.n_embd // config.expansion
        self.experts = ParallelExperts(n_routed_experts, config.n_embd, expert_dim)
        self.output_experts = ParallelExperts(n_routed_experts, expert_dim, config.n_embd)

        # Cutoff tracking for threshold mode
        # cutoff_ema: EMA of top-k cutoffs (min logit among selected tokens per expert)
        self.register_buffer('cutoff_ema', torch.zeros(n_routed_experts))
        self.cutoff_accumulator = None  # List of cutoffs from micro-batches
    
    def _scatter_expert(self, x_flat: Tensor, indices_batched: Tensor, weights_batched: Tensor, normalizer: Tensor, n_tokens: int, valid_mask: Tensor = None) -> Tensor:
        """
        Overriding the parent class's _scatter_expert method to use the scatter_atomic kernel.
        """
        