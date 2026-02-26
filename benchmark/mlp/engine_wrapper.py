"""Engine + scatter composition for benchmarking."""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor


class EngineWithScatter(nn.Module):
    """Compose ExpertEngine with scatter backend for benchmarking.

    This wrapper mimics the model forward pattern (engine + scatter)
    and returns only the output tensor (not metrics) for simpler autograd benchmarking.
    """

    def __init__(self, engine: nn.Module, scatter, routing_mode: str, is_shared: bool):
        """Initialize wrapper.

        Args:
            engine: ExpertEngine instance
            scatter: Scatter backend (IndexAddScatter or CSRScatter)
            routing_mode: 'topk' or 'threshold'
            is_shared: Whether shared expert exists (affects normalization)
        """
        super().__init__()
        self.engine = engine
        self.scatter = scatter
        self.routing_mode = routing_mode
        self.is_shared = is_shared

    def forward(self, x: Tensor) -> Tensor:
        """Forward pass returning only output tensor.

        Args:
            x: Input tensor (B, T, C)

        Returns:
            Output tensor (B, T, C)
        """
        # Reset accumulator to prevent list growth during benchmarking loops
        # (prevents recompilation with torch.compile)
        if self.training and hasattr(self.engine, 'cutoff_accumulator'):
            self.engine.cutoff_accumulator = None

        B, T, C = x.shape
        n_tokens = B * T

        # Route and compute expert outputs (unweighted)
        method = getattr(self.engine, f'forward_{self.routing_mode}')
        h_flat, indices_batched, weights_flat, normalizer, metrics = method(x, layer_idx=0, is_shared=self.is_shared)

        # Scatter applies weights during aggregation (fused operation)
        output = self.scatter(h_flat, indices_batched, n_tokens, weights_flat)

        return output.view(B, T, C)
