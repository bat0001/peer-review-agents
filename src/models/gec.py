"""GEC (Global Expert Choice): Routed experts only, no shared expert.

GEC is a sparse MoE architecture where experts select top-k tokens. Each expert processes
exactly k = ⌊BT/E⌋ tokens, achieving perfect load balancing.

This implementation is a thin wrapper around ExpertEngine, which handles routing
and expert computation. The wrapper handles scatter via composition (scatter_backends).
"""

from typing import Dict, Tuple

import torch
from torch import Tensor

from .model_base import BaseMLP
from .engines import ExpertEngine
from .engines.parallel_experts_manual import ParallelExperts
from src.ops.scatter_backends import get_scatter


class GECMLP(BaseMLP):
    """GEC MLP: Routed experts only (no shared expert).

    Routing modes:
    - topk (default training): Perfect load balance, differentiable
    - threshold (default eval): Causal routing using learned cutoff EMAs

    The model composes ExpertEngine (for routing + expert computation) with
    scatter backends (for aggregating expert outputs to tokens).
    """

    def __init__(self, config):
        super().__init__(config)

        # Create engine with all experts as routed (no shared expert)
        n_routed_experts = config.n_experts
        if config.expert_parallel:
            self.engine = ParallelExperts(config, n_routed_experts=n_routed_experts)
        else:
            self.engine = ExpertEngine(config, n_routed_experts=n_routed_experts)

        # Scatter backend (config.scatter_backend: 'index_add', 'index_add_fp32', 'csr', or 'csr_optimized')
        # max_fanout = n_experts (all experts are routed)
        self.scatter = get_scatter(config.scatter_backend, config.n_experts)

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
            h_flat, indices_flat, weights_flat, fanout, _shared_weights, metrics = self.engine.forward_threshold(x, layer_idx, is_shared=False)
        else:
            h_flat, indices_flat, weights_flat, fanout, _shared_weights, metrics = self.engine.forward_topk(x, layer_idx, is_shared=False)

        # Normalize weights (fanout by default, optional none)
        normalization_mode = getattr(self.config, 'normalization_mode', 'fanout')
        if normalization_mode == "fanout":
            # fanout[indices] is always >= 1 since selected tokens have at least 1 expert
            fanout_flat = fanout[indices_flat]  # (total_active,)
            normalized_weights = weights_flat / fanout_flat  # (total_active,)
        elif normalization_mode == "none":
            normalized_weights = weights_flat
        else:
            raise ValueError(f"Unknown normalization_mode: {normalization_mode}")

        # Scatter expert outputs to tokens (with normalized weights)
        output = self.scatter(h_flat, indices_flat, n_tokens, normalized_weights)

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
