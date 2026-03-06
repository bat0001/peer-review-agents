"""Unified expert-threshold wrapper implementing EC and ET routing."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from .engines import ExpertEngine
from .engines.parallel_experts_manual import ParallelExperts
from .model_base import BaseMLP
from src.ops.index_add_fp32 import IndexAddScatterFP32


@dataclass
class RoutePlan:
    """Pre-scatter routing payload returned by engine backends."""

    h_flat: Tensor
    indices_flat: Tensor
    weights_flat: Tensor
    fanout: Tensor
    shared_weights: Optional[Tensor]
    metrics: Dict[str, Tensor]


class ExpertThresholdChoiceMLP(BaseMLP):
    """Unified routed-expert MLP implementing EC top-k and ET threshold routing."""

    def __init__(self, config):
        super().__init__(config)

        self.shared_expert = bool(getattr(config, "shared_expert", False))
        self.routing_chunk_seqs = getattr(config, "routing_chunk_seqs", None)

        if self.routing_chunk_seqs is not None and bool(getattr(config, "expert_parallel", False)):
            raise ValueError("routing_chunk_seqs with expert_parallel is not supported in this release")

        n_routed_experts = config.n_experts - 1 if self.shared_expert else config.n_experts
        if config.expert_parallel:
            self.engine = ParallelExperts(config, n_routed_experts=n_routed_experts)
        else:
            self.engine = ExpertEngine(config, n_routed_experts=n_routed_experts)

        self.scatter = IndexAddScatterFP32()
        if self.shared_expert:
            self.shared_weight1 = nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            self.shared_weight2 = nn.Parameter(torch.empty(config.n_embd, config.expert_dim))

        self.selection_policy = getattr(
            config,
            "selection_policy",
            getattr(config, "routing_mode", "topk"),
        )
        self.routing_mode = self.selection_policy

    def _shared_expert_forward(self, x_flat: Tensor) -> Tensor:
        h = torch.mm(x_flat, self.shared_weight1.t())
        h = F.relu(h).square()
        return torch.mm(h, self.shared_weight2.t())

    def _select_routes(self, x: Tensor, layer_idx: int, policy: str) -> RoutePlan:
        result = self.engine.forward(
            x,
            layer_idx=layer_idx,
            is_shared=self.shared_expert,
            policy=policy,
            routing_chunk_seqs=self.routing_chunk_seqs,
        )
        return RoutePlan(*result)

    def _scatter_routes(self, x: Tensor, route: RoutePlan) -> Tuple[Tensor, Dict[str, Tensor]]:
        B, T, C = x.shape
        n_tokens = B * T

        if self.shared_expert:
            shared_weights = route.shared_weights if route.shared_weights is not None else torch.ones_like(route.fanout)
            shared_flat = self._shared_expert_forward(x.view(-1, C))
            output = self.scatter(
                route.h_flat,
                route.indices_flat,
                n_tokens,
                route.weights_flat,
                shared_flat=shared_flat,
                shared_weights=shared_weights,
            )
            route.metrics["expert_usage"] = torch.cat(
                [torch.ones(1, device=route.metrics["expert_usage"].device), route.metrics["expert_usage"]]
            )
        else:
            output = self.scatter(route.h_flat, route.indices_flat, n_tokens, route.weights_flat)

        return output.view(B, T, C).to(x.dtype), route.metrics

    def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        policy = "threshold" if (not self.training or self.selection_policy == "threshold") else "topk"
        route = self._select_routes(x, layer_idx, policy=policy)
        return self._scatter_routes(x, route)

    def finalize_cutoff_accumulation(self, apply_update: bool = True):
        self.engine.finalize_cutoff_accumulation(apply_update=apply_update)

    @property
    def cutoff_ema(self) -> Tensor:
        return self.engine.cutoff_ema

    @property
    def cutoff_ema_raw(self) -> Tensor:
        return self.engine.cutoff_ema_raw

    def sync_cutoff_state(self) -> Tensor:
        return self.engine.sync_cutoff_state()
