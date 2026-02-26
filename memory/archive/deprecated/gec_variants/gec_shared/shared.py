"""Global Expert Choice (GEC) with Shared Expert implementation.

Similar to DeepSeekMoE, this combines a shared expert that processes all tokens
with routed experts using the GEC (Global Expert Choice) mechanism.
"""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..model_base import BaseMLP, ModelConfig, RouterMixin
from ...utils import compute_routing_metrics


class GECSharedMLP(BaseMLP, RouterMixin):
    """Global Expert Choice MLP with a shared expert.

    Architecture:
    - One shared expert that processes all tokens (always active)
    - Multiple routed experts that use GEC mechanism (experts select tokens)
    - Final output = shared_output + routed_output

    Memory usage for routed experts scales as O(n_routed_experts * selection_rate * batch_size * seq_length).
    The shared expert always processes all tokens.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        # Ensure required parameters are not None
        assert config.n_experts is not None, "n_experts must be specified for GEC"
        assert config.expert_dim is not None, "expert_dim must be specified for GEC"
        assert config.shared_expert_dim is not None, "shared_expert_dim must be specified for GEC"

        # Number of routed experts (excluding shared expert)
        # For GEC shared: config.n_experts = (G × E) + 1, so n_routed = (G × E)
        self.n_routed_experts = config.n_experts - 1
        assert self.n_routed_experts > 0, "Need at least 1 routed expert"
        assert self.n_routed_experts % 8 == 0, f"n_routed_experts must be divisible by 8, got {self.n_routed_experts}"

        # Routing mode: None (auto), 'topk', or 'threshold'
        self.routing_mode = getattr(config, 'routing_mode', None)
        if self.routing_mode is not None and self.routing_mode not in ['topk', 'threshold']:
            raise ValueError(f"routing_mode must be None, 'topk', or 'threshold', got: {self.routing_mode}")
        
        # Shared expert parameters (always active) - no bias! (nanochat style)
        self.shared_weight1 = nn.Parameter(
            torch.randn(config.shared_expert_dim, config.n_embd) * 0.02
        )
        self.shared_weight2 = nn.Parameter(
            torch.randn(config.n_embd, config.shared_expert_dim) * 0.02
        )

        # Router layer (one per routed expert) - no bias! (nanochat style)
        self.router = nn.Linear(config.n_embd, self.n_routed_experts, bias=False)

        # Routed expert parameters - convert to ParameterList of 2D tensors
        # Use torch.empty() since init_weights() will initialize them properly
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(self.n_routed_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(self.n_routed_experts)
        ])

        # No separate activation module - use ReLU² inline (nanochat style)
        
        # Moving average of cutoff values per routed expert
        # Initialize to 1.0 instead of 0 A very high value to avoid OOM
        self.register_buffer('cutoff_ema', torch.full((self.n_routed_experts,), 1.0))
        self.register_buffer('cutoff_ema_count', torch.zeros(1))  # For unbiased correction
        self.ema_decay = 0.99  # EMA decay rate

        # Cutoff accumulator for gradient accumulation (step-boundary pattern)
        self.cutoff_accumulator = None  # Will be list of tensors during accumulation

        # Representative layers for detailed metrics tracking
        self.repr_layers = {0, config.n_layer//4, config.n_layer//2, 3*config.n_layer//4, config.n_layer-1}
        self.temporal_window = getattr(config, 'temporal_window', 100)
        self.temporal_warmup = getattr(config, 'temporal_warmup', 10)

        # Temporal buffers for representative layers (use n_routed_experts)
        for layer in self.repr_layers:
            self.register_buffer(f'cutoff_history_L{layer}', torch.zeros(self.temporal_window, self.n_routed_experts))
            self.register_buffer(f'history_idx_L{layer}', torch.tensor(0))
            self.register_buffer(f'prev_cutoff_L{layer}', torch.zeros(self.n_routed_experts))

    def _shared_expert_forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass for shared expert (nanochat style: no bias, ReLU²)."""
        h = F.linear(x, self.shared_weight1)
        h = F.relu(h).square()  # ReLU² (nanochat style)
        h = F.linear(h, self.shared_weight2)
        return h

    def _expert_forward(self, x: torch.Tensor, expert_idx: int) -> torch.Tensor:
        """Forward pass for a single routed expert (nanochat style: no bias, ReLU²)."""
        h = F.linear(x, self.expert_weight1[expert_idx])
        h = F.relu(h).square()  # ReLU² (nanochat style)
        h = F.linear(h, self.expert_weight2[expert_idx])
        return h

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Dispatcher: calls topk or threshold forward based on routing mode.

        Routing mode selection:
        - None (default): auto-switch based on self.training (topk in train, threshold in eval)
        - 'topk': always use topk routing (perfect load balance, differentiable)
        - 'threshold': always use threshold routing (causal, dynamic)
        """
        # Determine effective routing mode
        if self.routing_mode is None:
            # Auto mode: topk for training, threshold for eval
            mode = 'topk' if self.training else 'threshold'
        else:
            # Explicit override
            mode = self.routing_mode

        if mode == 'topk':
            return self.forward_topk(x, layer_idx)
        else:  # mode == 'threshold'
            return self.forward_threshold(x, layer_idx)

    def forward_topk(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with global top-k routing (perfect load balance)."""
        B, T, C = x.shape
        n_routed_experts = self.n_routed_experts
        
        # Process shared expert (all tokens)
        x_flat = x.view(-1, C)  # (B*T, C)
        
        # Shared expert forward pass (nanochat style: no bias, ReLU²)
        shared_h = F.linear(x_flat, self.shared_weight1)  # (B*T, expert_dim)
        shared_h = F.relu(shared_h).square()  # ReLU² (nanochat style)
        shared_output = F.linear(shared_h, self.shared_weight2)  # (B*T, C)
        
        # Compute routing scores for all tokens to all routed experts
        router_logits = self.router(x)  # (B, T, n_routed_experts)
        
        # Flatten for global selection
        router_logits_flat = router_logits.view(-1, n_routed_experts)  # (B*T, n_routed_experts)
        n_tokens = B * T
        
        # Use topk for exact k tokens per expert (compute-matching)
        # Formula: k = n_tokens × (G-1) // (G×E) ensures G-1 routed experts active per token
        G = self.config.granularity
        E = self.config.expansion
        k = int(n_tokens * (G - 1) // (G * E))
        
        # Select top-k tokens for ALL routed experts in parallel (on raw logits)
        topk_values, topk_indices = torch.topk(router_logits_flat.t(), k=min(k, n_tokens), dim=1)  # (n_routed_experts, k)
        
        # Get cutoff values (last selected token's probability for each expert)
        cutoffs = topk_values[:, -1]  # (n_routed_experts,)
        
        # Update moving averages (for metrics only)
        with torch.no_grad():
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
            self.cutoff_ema_count += 1
        
        # Process routed experts
        # Create permutation indices
        permutation_indices = topk_indices.reshape(-1)  # (n_routed_experts * k,)
        
        # Permute input tokens
        x_permuted = x_flat[permutation_indices]  # (n_routed_experts * k, C)
        
        # Reshape to separate experts: (n_routed_experts, k, C)
        x_permuted = x_permuted.view(n_routed_experts, k, C)

        # Stack 2D parameters to 3D before batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        # First layer: x -> hidden (nanochat style: no bias, ReLU²)
        h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))  # (n_routed_experts, k, expert_dim)
        h = F.relu(h).square()  # ReLU² (nanochat style)

        # Second layer: hidden -> output (nanochat style: no bias)
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (n_routed_experts, k, C)
        
        # Apply soft weights from router (activate the selected logits)
        weights = self.apply_router_activation(topk_values, self.config.router_activation).view(n_routed_experts, k, 1)  # (n_routed_experts, k, 1)

        # Compute normalizer using mixin method (baseline=0.0 for routed experts only)
        normalizer = self.compute_normalizer(
            mode=self.config.normalization_mode,
            n_tokens=n_tokens,
            indices=permutation_indices,
            weights=weights.view(-1),
            router_logits_flat=router_logits_flat,
            router_activation=self.config.router_activation,
            device=x.device,
            baseline=0.0
        )  # (n_tokens,)

        # Add 1.0 for shared expert (always active with implicit weight=1.0)
        normalizer = normalizer + 1.0

        # Normalize h BEFORE scatter (compile will fuse with scatter)
        normalizer_h = normalizer[permutation_indices].view(n_routed_experts, k, 1)
        h = h * weights / normalizer_h

        # Flatten back
        h = h.view(-1, C)  # (n_routed_experts * k, C)

        # Scatter routed output
        # Create buffer in same dtype as shared_output (BF16 under autocast)
        routed_output = torch.zeros_like(shared_output)
        routed_output.index_add_(0, permutation_indices, h.to(routed_output.dtype))

        # Normalize shared expert output by the same normalizer
        # Cast normalizer to match shared_output's dtype
        shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)

        # Combine shared and routed outputs (both pre-normalized)
        output = shared_output + routed_output

        # Reshape back
        output = output.view(B, T, C)

        # Compute metrics using unified method
        token_fanout = torch.zeros(n_tokens, device=x.device)
        ones = torch.ones(len(permutation_indices), device=x.device)
        token_fanout.scatter_add_(0, permutation_indices, ones)

        # All routed experts process exactly k tokens
        expert_token_counts = torch.full((n_routed_experts,), k, device=x.device)

        # For GEC_shared: expert_usage includes shared expert (1.0) + routed experts
        # avg_experts_per_token includes shared (1.0 + routed avg)
        total_expert_usage = torch.cat([
            torch.ones(1, device=x.device),  # Shared expert processes all tokens
            expert_token_counts / n_tokens    # Routed experts
        ])

        # Adjust token_fanout to include shared expert (always active)
        token_fanout_with_shared = token_fanout + 1.0  # Every token has shared expert

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,
            cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
            weights=weights.view(-1),
            router_logits_flat=router_logits_flat,
            token_fanout=token_fanout_with_shared,  # Include shared expert in fanout
            expert_usage=total_expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=normalizer,
            indices=permutation_indices,
            normalization_mode=self.config.normalization_mode,
        )

        # Add raw layer data for visualization (during eval only)
        if not torch.is_grad_enabled():
            metrics['layer_data'] = {
                'weights': weights.view(-1).detach(),
                'fanout': token_fanout_with_shared.detach(),
                'cutoffs': cutoffs.detach(),
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics

    def forward_threshold(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with learned threshold routing for routed experts (causal).

        WARNING: No backward pass support. Use forward_topk() for training.
        """
        assert not torch.is_grad_enabled(), \
            "Threshold routing does not support backward pass. Use forward_topk() for training."

        B, T, C = x.shape
        n_routed_experts = self.n_routed_experts
        n_tokens = B * T

        # Flatten
        x_flat = x.view(-1, C)  # (B*T, C)

        # Shared expert (always active for all tokens)
        shared_output = self._shared_expert_forward(x_flat)  # (B*T, C)

        # Compute routing scores for routed experts
        router_logits = self.router(x)  # (B, T, n_routed_experts)
        router_logits_flat = router_logits.view(-1, n_routed_experts)  # (B*T, n_routed_experts)

        # Only fanout normalization mode is optimized
        if self.config.normalization_mode != 'fanout':
            raise NotImplementedError(
                f"Threshold routing only supports normalization_mode='fanout', got '{self.config.normalization_mode}'"
            )

        # Loop 1: Compute normalizer incrementally
        normalizer = torch.zeros(n_tokens, device=x.device, dtype=torch.float32)

        for expert_idx in range(n_routed_experts):
            mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]  # type: ignore
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            normalizer.index_add_(0, active_indices, weights.float())

        # Add shared expert contribution
        normalizer = normalizer + 1.0

        # Normalize shared output once
        shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)

        # Loop 2: Process experts and accumulate directly (NO intermediate buffers!)
        token_fanout = torch.zeros(n_tokens, device=x.device)

        for expert_idx in range(n_routed_experts):
            mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]  # type: ignore
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            # Process expert
            x_active = x_flat[active_indices]
            h = self._expert_forward(x_active, expert_idx)

            # Apply router activation
            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            # Normalize by per-token normalizer
            normalizer_h = normalizer[active_indices].unsqueeze(-1).to(h.dtype)
            h_weighted = h * weights.unsqueeze(-1) / normalizer_h

            # Add directly into shared_output (no intermediate buffer!)
            shared_output.index_add_(0, active_indices, h_weighted.to(shared_output.dtype))

            # Track token fanout for metrics
            ones = torch.ones(len(active_indices), device=x.device)
            token_fanout.scatter_add_(0, active_indices, ones)

        output = shared_output

        # Reshape back
        output = output.view(B, T, C)

        # Include shared expert in fanout (token_fanout already computed in both paths)
        token_fanout_with_shared = token_fanout + 1.0

        # Compute expert token counts
        expert_token_counts = torch.zeros(n_routed_experts, device=x.device)
        for e in range(n_routed_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e > self.cutoff_ema[e]).float().sum()  # type: ignore

        # Expert usage includes shared (1.0) + routed
        total_expert_usage = torch.cat([
            torch.ones(1, device=x.device),  # Shared expert processes all tokens
            expert_token_counts / n_tokens    # Routed experts
        ])

        metrics = {
            'gec_shared_expert_usage': total_expert_usage,
            'gec_shared_avg_experts_per_token': token_fanout_with_shared.mean(),
            'gec_shared_cutoff_ema': self.cutoff_ema.clone(),  # type: ignore
            'gec_shared_max_experts_per_token': token_fanout_with_shared.max(),
            'gec_shared_min_experts_per_token': token_fanout_with_shared.min(),
        }

        # Add raw layer data for visualization (during eval only)
        # Threshold routing is eval-only, so always collect layer_data
        if not torch.is_grad_enabled():
            # Compute weights for visualization (matches topk - use proper router activation)
            weights_viz = self.apply_router_activation(router_logits_flat, self.config.router_activation)
            metrics['layer_data'] = {
                'weights': weights_viz.view(-1).detach(),
                'fanout': token_fanout_with_shared.detach(),
                'cutoffs': self.cutoff_ema.clone().detach(),  # type: ignore
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics

    def finalize_cutoff_accumulation(self):
        """Finalize cutoff accumulation at training step boundary.

        Computes arithmetic mean of accumulated topk cutoffs from all micro-batches
        in the current step, then updates the cutoff EMA with this mean.

        This should be called once per training step, after all gradient accumulation
        micro-batches complete (via BaseGPT.step_complete()).

        Note: This is a no-op if no cutoffs were accumulated (e.g., during eval or topk mode).
        """
        if self.cutoff_accumulator is not None and len(self.cutoff_accumulator) > 0:
            # Stack all accumulated cutoffs: [n_micro_batches, n_routed_experts]
            stacked_cutoffs = torch.stack(self.cutoff_accumulator, dim=0)

            # Compute arithmetic mean across micro-batches: [n_routed_experts]
            avg_cutoffs = stacked_cutoffs.mean(dim=0)

            # Update EMA with averaged cutoffs
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * avg_cutoffs
            self.cutoff_ema_count += 1

            # Clear accumulator for next step
            self.cutoff_accumulator = None
