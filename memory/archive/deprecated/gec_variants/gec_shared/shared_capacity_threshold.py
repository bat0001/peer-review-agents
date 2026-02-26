"""GEC_shared with capacity-aware trainable threshold routing."""

from typing import Dict, Tuple

import torch
import torch.nn.functional as F
from torch import Tensor

from .shared import GECSharedMLP
from ...utils import compute_routing_metrics


class GECSharedMLPCapacityThreshold(GECSharedMLP):
    """GEC_shared with capacity-constrained threshold routing for training.

    Extends GECSharedMLP with capacity-aware threshold routing:
    - Training mode: Dual-path (top-k for EMA + capacity-bounded threshold for routing)
    - Eval mode: Pure threshold (same as parent, no capacity constraints)

    Key difference from GECSharedMLPTrainableThreshold:
    - Enforces hard capacity bounds: [k×(1-cap), k×(1+cap)]
    - Each expert selects tokens in this range regardless of threshold
    - Tracks capacity hit rates for monitoring

    Backward compatible with parent GECSharedMLP for top-k routing.
    """

    def __init__(self, config):
        super().__init__(config)
        # Override cutoff_ema initialization: use very negative value
        # so that in threshold mode, experts can actually activate initially
        self.cutoff_ema.fill_(-10.0)
    
    def step_complete(self, step: int, threshold_warmup_steps: int):
        """Complete training step operations.

        Args:
            step: Current training step number
            threshold_warmup_steps: Warmup steps from config (-1 if disabled)

        This method is now a thin wrapper that delegates to the parent BaseGPT.step_complete,
        which handles finalization and sync via duck-typed methods on each router.
        """
        # Call parent implementation which handles:
        # 1. Finalize cutoff accumulation (via finalize_cutoff_accumulation)
        # 2. Sync cutoff EMA across GPUs (via sync_cutoff_state)
        super().step_complete(step, threshold_warmup_steps)

    def forward(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Dispatcher: calls topk or threshold forward based on routing mode.

        Routing mode selection:
        - None (default): auto-switch based on self.training (topk in train, threshold in eval)
        - 'topk': always use topk routing (perfect load balance, differentiable)
        - 'threshold': always use threshold routing (causal, dynamic, capacity-bounded in training)
        """
        # Determine effective routing mode
        if self.routing_mode is None:
            # Auto mode: topk for training, threshold for eval
            mode = 'topk' if self.training else 'threshold'
        else:
            # Explicit override
            mode = self.routing_mode

        if mode == 'topk':
            # Call parent's forward_topk (standard top-k routing)
            return super().forward_topk(x, layer_idx)
        else:  # mode == 'threshold'
            # Call our override (capacity-aware in training, pure threshold in eval)
            return self.forward_threshold(x, layer_idx)

    def forward_threshold(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Threshold routing with capacity constraints during training.

        Training mode (capacity-aware):
          1. Top-k (no_grad) to extract cutoffs for EMA updates
          2. Capacity-bounded threshold routing (with gradients) for actual computation
             - Each expert processes k ∈ [k_min, k_max] tokens
             - k_min = k_target × (1 - capacity_factor)
             - k_max = k_target × (1 + capacity_factor)

        Eval mode:
          - Pure threshold routing (no capacity constraints, no top-k overhead)
        """
        B, T, C = x.shape
        n_routed_experts = self.n_routed_experts
        n_tokens = B * T

        # Flatten
        x_flat = x.view(-1, C)  # (B*T, C)

        # Compute router logits (needed for both training and eval)
        router_logits = self.router(x)  # (B, T, n_routed_experts)
        router_logits_flat = router_logits.view(-1, n_routed_experts)  # (B*T, n_routed_experts)

        # === TRAINING: Parallel top-k for EMA + Capacity-aware threshold routing ===
        # Check if capacity constraints are enabled
        capacity_enabled = self.config.expert_capacity_factor >= 0 and self.training

        if self.training:
            # Compute k using GEC_shared formula (shared for EMA and capacity bounds)
            G = self.config.granularity
            E = self.config.expansion
            k_target = int(n_tokens * (G - 1) // (G * E))

            with torch.no_grad():
                # Compute cutoffs via top-k for EMA
                topk_values, _ = torch.topk(
                    router_logits_flat.t(), k=min(k_target, n_tokens), dim=1
                )
                cutoffs = topk_values[:, -1]  # (n_routed_experts,)

                # Accumulate cutoffs for averaging at step boundary
                # (EMA will be updated in step_complete())
                if self.cutoff_accumulator is None:
                    self.cutoff_accumulator = []
                self.cutoff_accumulator.append(cutoffs)

            # Capacity tracking (if enabled)
            if capacity_enabled:
                k_min = int(k_target * (1 - self.config.expert_capacity_factor))
                k_max = int(k_target * (1 + self.config.expert_capacity_factor))

                capacity_overflow = 0  # Experts hitting k_max
                capacity_underflow = 0  # Experts hitting k_min
                per_expert_capacity_status = []  # For repr layers
                actual_k_per_expert = []  # Track actual k selected
                # Note: would_have_k_per_expert removed - computed after loop to avoid gradient accumulation

        # === THRESHOLD ROUTING (capacity-aware if enabled) ===
        # Only fanout normalization mode is optimized
        if self.config.normalization_mode != 'fanout':
            raise NotImplementedError(
                f"Threshold routing only supports normalization_mode='fanout', got '{self.config.normalization_mode}'"
            )

        # Shared expert (always active for all tokens)
        shared_output = self._shared_expert_forward(x_flat)  # (B*T, C)

        # Loop 1: Capacity-bounded selection (determine which tokens each expert processes)
        selected_indices = {}
        selected_weights = {}

        for expert_idx in range(n_routed_experts):
            # Count tokens above threshold (keep as tensor to avoid .item() sync)
            above_mask = router_logits_flat[:, expert_idx] >= self.cutoff_ema[expert_idx]
            n_above = above_mask.sum()  # Keep as tensor

            if capacity_enabled:
                # TRAINING WITH CAPACITY: Capacity-bounded selection
                # Enforce capacity bounds (using tensor operations)
                k_actual = torch.clamp(n_above, k_min, k_max)

                # Determine status based on bounds (keep as tensors as long as possible)
                # Use tensor comparisons instead of Python ints
                hit_max = n_above > k_max
                hit_min = n_above < k_min

                if hit_max:
                    status = 2  # hit_max
                    capacity_overflow += 1
                    # Select top-k tokens (need int for topk)
                    k_int = int(k_actual)
                    if k_int > 0:
                        _, active_indices = torch.topk(
                            router_logits_flat[:, expert_idx],
                            k=k_int
                        )
                    else:
                        active_indices = torch.tensor([], dtype=torch.long, device=x.device)
                elif hit_min:
                    status = 0  # hit_min
                    capacity_underflow += 1
                    # Select top-k tokens (need int for topk)
                    k_int = int(k_actual)
                    if k_int > 0:
                        _, active_indices = torch.topk(
                            router_logits_flat[:, expert_idx],
                            k=k_int
                        )
                    else:
                        active_indices = torch.tensor([], dtype=torch.long, device=x.device)
                else:
                    status = 1  # within bounds
                    # Use mask directly (no int() needed)
                    active_indices = above_mask.nonzero(as_tuple=False).squeeze(-1)

                per_expert_capacity_status.append(status)
                actual_k_per_expert.append(k_actual)
            else:
                # PURE THRESHOLD: No capacity constraints (training or eval)
                active_indices = above_mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            # Compute weights for this expert
            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            selected_indices[expert_idx] = active_indices
            selected_weights[expert_idx] = weights

        # Compute above_counts for capacity metrics (vectorized, no gradient accumulation)
        if capacity_enabled:
            with torch.no_grad():
                above_mask_all = router_logits_flat >= self.cutoff_ema.unsqueeze(0)  # (B*T, n_routed_experts)
                above_counts_tensor = above_mask_all.sum(dim=0)  # (n_routed_experts,)

        # Loop 2: Compute normalizer incrementally
        normalizer = torch.zeros(n_tokens, device=x.device, dtype=torch.float32)

        for expert_idx in selected_indices.keys():
            normalizer.index_add_(0, selected_indices[expert_idx], selected_weights[expert_idx].float())

        # Add shared expert contribution
        normalizer = normalizer + 1.0

        # Normalize shared output once
        shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)

        # Loop 3: Process experts and accumulate directly (NO intermediate expert_outputs buffer!)
        token_fanout = torch.zeros(n_tokens, device=x.device)

        for expert_idx in selected_indices.keys():
            active_indices = selected_indices[expert_idx]
            weights = selected_weights[expert_idx]

            # Process tokens (gradients flow here in training)
            x_active = x_flat[active_indices]
            h = self._expert_forward(x_active, expert_idx)

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

        # Include shared expert in fanout (token_fanout already computed in Loop 3)
        token_fanout_with_shared = token_fanout + 1.0

        # Compute expert token counts
        expert_token_counts = torch.zeros(n_routed_experts, device=x.device)
        for e in range(n_routed_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e >= self.cutoff_ema[e]).float().sum()

        # Expert usage includes shared (1.0) + routed
        total_expert_usage = torch.cat([
            torch.ones(1, device=x.device),  # Shared expert processes all tokens
            expert_token_counts / n_tokens    # Routed experts
        ])

        # Prepare data for compute_routing_metrics
        # Collect weights and indices from selected dicts
        if selected_indices:
            all_weights = []
            all_indices = []
            for expert_idx in sorted(selected_indices.keys()):
                all_weights.append(selected_weights[expert_idx])
                all_indices.append(selected_indices[expert_idx])
            weights = torch.cat(all_weights) if all_weights else torch.zeros(0, device=x.device)
            indices = torch.cat(all_indices) if all_indices else torch.zeros(0, device=x.device, dtype=torch.long)
        else:
            weights = torch.zeros(0, device=x.device)
            indices = torch.zeros(0, device=x.device, dtype=torch.long)

        # Get instant cutoffs (from training topk or use EMA for eval)
        if self.training and self.cutoff_accumulator:
            # Use the most recent topk cutoffs from training
            instant_cutoffs = self.cutoff_accumulator[-1] if self.cutoff_accumulator else self.cutoff_ema.clone()
        else:
            # In eval or if no accumulator, use EMA as instant cutoffs
            instant_cutoffs = self.cutoff_ema.clone()

        # Compute all routing metrics (including capacity if enabled)
        # Note: above_counts_tensor is already computed after Loop 1 (no gradient accumulation)
        if not capacity_enabled:
            above_counts_tensor = None

        metrics = compute_routing_metrics(
            cutoffs=instant_cutoffs,
            cutoff_ema=self.cutoff_ema.clone(),
            weights=weights,
            router_logits_flat=router_logits_flat,
            token_fanout=token_fanout_with_shared,  # Include shared expert
            expert_usage=total_expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=normalizer,
            indices=indices,
            normalization_mode=self.config.normalization_mode,
            above_counts=above_counts_tensor,
            k_min=k_min if capacity_enabled else None,
            k_max=k_max if capacity_enabled else None,
        )

        return output, metrics
