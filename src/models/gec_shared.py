"""GEC_shared: Routed experts + always-active shared expert.

GEC_shared extends GEC by adding a shared expert that processes all tokens.
The shared expert provides a baseline capacity while routed experts add specialization.

Formula for k: k = n_tokens × (G-1) / (G×E) (leaves room for shared expert)

The scatter backend applies ALL weights in one fused pass:
- Routed: output[idx] += h_flat[slot] * weights_flat[slot]
- Shared: output[idx] += shared_flat[idx] * shared_weights[idx]
"""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from .model_base import BaseMLP
from .engines import ExpertEngine
from .engines.parallel_experts_manual import ParallelExperts
from src.ops.scatter_backends import get_scatter


class GECSharedMLP(BaseMLP):
    """GEC_shared MLP: Routed experts + always-active shared expert.

    Architecture:
    - n_experts = (G × E) total, with (G × E - 1) routed + 1 shared
    - Shared expert processes all tokens (implicit weight=1.0)
    - Routed experts selected via topk or threshold routing
    - Outputs normalized consistently (normalizer = fanout + 1 for shared expert)

    Routing modes:
    - topk (default training): Perfect load balance for routed experts
    - threshold (default eval): Causal routing with optional capacity constraints

    The wrapper composes ExpertEngine (for routing + expert computation) with
    scatter backends (for aggregating expert outputs). Uses scatter's add_into
    to fuse routed output aggregation with shared expert output.
    """

    def __init__(self, config):
        super().__init__(config)

        # Routed expert engine (reserves one expert slot for shared)
        n_routed_experts = config.n_experts - 1
        if config.expert_parallel:
            self.engine = ParallelExperts(config, n_routed_experts=n_routed_experts)
        else:
            self.engine = ExpertEngine(config, n_routed_experts=n_routed_experts)

        # Scatter backend (config.scatter_backend: 'index_add', 'index_add_fp32', 'csr', or 'csr_optimized')
        # max_fanout = n_routed_experts (shared expert handled separately)
        max_fanout = config.n_experts - 1
        self.scatter = get_scatter(config.scatter_backend, max_fanout)

        # Shared expert (always active, simple dense MLP)
        self.shared_weight1 = nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
        self.shared_weight2 = nn.Parameter(torch.empty(config.n_embd, config.expert_dim))

        # Routing mode control (training only; eval always uses threshold)
        self.routing_mode = getattr(config, 'routing_mode', 'topk')

    def _shared_expert_forward(self, x_flat: Tensor) -> Tensor:
        """Shared expert forward pass (nanochat style: no bias, ReLU²).

        Args:
            x_flat: (B*T, C)

        Returns:
            output: (B*T, C)
        """
        # First layer: x @ W1^T
        h = torch.mm(x_flat, self.shared_weight1.t())

        # Activation: ReLU²
        h = F.relu(h).square()

        # Second layer: h @ W2^T
        output = torch.mm(h, self.shared_weight2.t())

        return output

    def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Forward pass combining shared expert and routed experts.

        Flow:
        1. Engine computes routed expert outputs (h_flat, weights_flat, indices, shared_weights, metrics)
        2. Compute shared expert output (unweighted)
        3. Apply normalization based on config (fanout or none)
        4. Scatter applies ALL weights in one fused pass (routed + shared)

        Args:
            x: Input tensor (B, T, C)
            layer_idx: Layer index for metrics

        Returns:
            output: (B, T, C)
            metrics: Dictionary of routing metrics
        """
        B, T, C = x.shape
        n_tokens = B * T
        x_flat = x.view(-1, C)

        # === Get routed expert outputs (pre-scatter, UNWEIGHTED) ===
        # Engine returns 6-tuple: h_flat, indices_flat, weights_flat, fanout, engine_shared_weights, metrics
        if not self.training or self.routing_mode == 'threshold':
            h_flat, indices_flat, weights_flat, fanout, engine_shared_weights, metrics = self.engine.forward_threshold(x, layer_idx, is_shared=True)
        else:
            h_flat, indices_flat, weights_flat, fanout, engine_shared_weights, metrics = self.engine.forward_topk(x, layer_idx, is_shared=True)

        # === Apply normalization based on config ===
        normalization_mode = getattr(self.config, 'normalization_mode', 'fanout')

        if normalization_mode == "fanout":
            # Standard fanout normalization: divide by (fanout + 1)
            one = torch.tensor(1.0, device=fanout.device, dtype=fanout.dtype)
            normalizer = fanout + one  # (B*T,)
            normalizer_flat = normalizer[indices_flat]  # (total_active,)
            normalized_weights = weights_flat / normalizer_flat  # (total_active,)
            shared_weights = one / normalizer  # (B*T,)

        elif normalization_mode == "none":
            # No normalization: use weights as-is
            # For softmax_e variants, weights are already properly normalized
            normalized_weights = weights_flat
            if engine_shared_weights is None:
                # Keep shared expert unweighted for non-softmax activations.
                shared_weights = torch.ones_like(fanout)
            else:
                shared_weights = engine_shared_weights  # From engine (softmax or 1/G)

        else:
            raise ValueError(f"Unknown normalization_mode: {normalization_mode}")

        # === Compute shared expert output (UNWEIGHTED) ===
        shared_flat = self._shared_expert_forward(x_flat)  # (B*T, C)

        # === Scatter applies ALL weights in one fused pass ===
        # Routed: output[idx] += h_flat[slot] * normalized_weights[slot]
        # Shared: output[idx] += shared_flat[idx] * shared_weights[idx]
        output = self.scatter(
            h_flat, indices_flat, n_tokens, normalized_weights,
            shared_flat=shared_flat, shared_weights=shared_weights
        )

        # === Update metrics to include shared expert ===
        metrics = self._update_metrics_with_shared(metrics, n_tokens)

        # Reshape to (B, T, C) and cast back to input dtype
        output = output.view(B, T, C).to(x.dtype)

        return output, metrics

    def _update_metrics_with_shared(self, metrics: Dict[str, Tensor], n_tokens: int) -> Dict[str, Tensor]:
        """Add shared expert to usage metrics.

        The shared expert processes all tokens, so we prepend 1.0 to expert_usage.

        Args:
            metrics: Metrics from engine (for routed experts only)
            n_tokens: Total number of tokens

        Returns:
            Updated metrics including shared expert
        """
        # expert_usage from engine: (n_routed_experts,)
        # Prepend 1.0 for shared expert (processes all tokens)
        metrics['expert_usage'] = torch.cat([
            torch.ones(1, device=metrics['expert_usage'].device),
            metrics['expert_usage']
        ])

        # token_fanout already accounts for shared expert (baseline=1.0 in normalizer)
        # No need to modify it here

        return metrics

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
            cutoff_ema_raw tensor (for routed experts only)
        """
        return self.engine.sync_cutoff_state()
