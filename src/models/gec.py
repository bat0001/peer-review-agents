"""GEC (Global Expert Choice): Routed experts only, no shared expert.

GEC is a sparse MoE architecture where experts select top-k tokens. Each expert processes
exactly k = ⌊BT/E⌋ tokens, achieving perfect load balancing.

This implementation is a thin wrapper around ExpertEngine, which handles routing
and expert computation. The wrapper uses a fixed FP32 index_add scatter.
"""

from typing import Dict, Tuple

import torch
from torch import Tensor

from .model_base import BaseMLP
from .engines import ExpertEngine
from .engines.parallel_experts_manual import ParallelExperts
from src.ops.index_add_fp32 import IndexAddScatterFP32


class GECMLP(BaseMLP):
    """GEC MLP: Routed experts only (no shared expert).

    Routing modes:
    - topk (default training): Perfect load balance, differentiable
    - threshold (default eval): Causal routing using learned cutoff EMAs

    The model composes ExpertEngine (for routing + expert computation) with
    FP32 index_add scatter (for aggregating expert outputs to tokens).
    """

    def __init__(self, config):
        super().__init__(config)

        # We intentionally keep two engine implementations:
        # - ExpertEngine: default routed-expert path
        # - ParallelExperts: EP-specific path when expert_parallel=true
        # This keeps EP communication logic isolated from the standard engine.
        # Create engine with all experts as routed (no shared expert)
        n_routed_experts = config.n_experts
        if config.expert_parallel:
            self.engine = ParallelExperts(config, n_routed_experts=n_routed_experts)
        else:
            self.engine = ExpertEngine(config, n_routed_experts=n_routed_experts)

        # Fixed scatter path: FP32 index_add accumulation.
        self.scatter = IndexAddScatterFP32()

        # Routing mode control (training only; eval always uses threshold)
        self.routing_mode = getattr(config, 'routing_mode', 'topk')

    def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Forward pass with routing mode dispatch.

        Args:
            x: Input tensor (B, T, C)
            layer_idx: Layer index for metrics

        Returns:
            output: (B, T, C)
            metrics: Dictionary of routing metrics
        """
        B, T, C = x.shape
        n_tokens = B * T

        # Dispatch to engine (is_shared=False since no shared expert)
        # Engine returns 6-tuple: h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics
        # We ignore shared_weights since GEC has no shared expert
        if not self.training or self.routing_mode == 'threshold':
            h_flat, indices_flat, weights_flat, _fanout, _shared_weights, metrics = self.engine.forward_threshold(x, layer_idx, is_shared=False)
        else:
            h_flat, indices_flat, weights_flat, _fanout, _shared_weights, metrics = self.engine.forward_topk(x, layer_idx, is_shared=False)

        # Scatter expert outputs to tokens using raw routed weights.
        output = self.scatter(h_flat, indices_flat, n_tokens, weights_flat)

        # Reshape output from (B*T, C) to (B, T, C) and cast back to input dtype
        output = output.view(B, T, C).to(x.dtype)

        return output, metrics

    def finalize_cutoff_accumulation(self, apply_update: bool = True):
        """Finalize cutoff accumulation (called by BaseGPT.step_complete)."""
        self.engine.finalize_cutoff_accumulation(apply_update=apply_update)

    @property
    def cutoff_ema(self) -> Tensor:
        """Effective (bias-corrected) cutoff used by routing and metrics."""
        return self.engine.cutoff_ema

    @property
    def cutoff_ema_raw(self) -> Tensor:
        """Raw EMA buffer used for synchronization/state."""
        return self.engine.cutoff_ema_raw

    def sync_cutoff_state(self) -> Tensor:
        """Return raw cutoff EMA buffer for syncing across GPUs.

        Returns:
            cutoff_ema_raw tensor
        """
        return self.engine.sync_cutoff_state()
