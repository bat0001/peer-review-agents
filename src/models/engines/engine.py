"""ExpertEngine: Core expert computation without scatter.

This module provides the core expert computation engine used by both GEC and GEC_shared.
It handles:
- Router logits computation
- Top-k and threshold-based token selection
- Batched expert MLP forward passes (BMM)
- Normalization
- Cutoff EMA tracking for threshold mode
- Capacity constraints (optional)

The engine returns pre-scatter, unweighted outputs:
    (h_flat, indices_batched, weights_flat, normalizer, metrics)

The wrapper classes (GEC, GEC_shared) scatter using their chosen backend, applying
weights during scatter. GEC_shared uses normalizer to compute shared expert weights.
"""

from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from ..router_utils import apply_router_activation, compute_fanout


class ExpertEngine(nn.Module):
    """Expert computation engine returning pre-scatter, unweighted outputs.

    This engine handles routed expert logic:
    - Routing decisions (top-k or threshold-based selection)
    - Expert computation (batched BMM)
    - Normalization
    - Cutoff EMA tracking

    Returns (h_flat, indices_batched, weights_flat, normalizer, metrics).
    The wrapper classes (GEC, GEC_shared) handle the scatter operation,
    applying weights during scatter. GEC_shared uses normalizer for shared
    expert weighting (shared_weights = 1/normalizer).

    Key parameters:
    - is_shared: Whether a shared expert exists (affects normalization baseline)
    - expert_capacity_factor: Enables capacity constraints in threshold mode
    """

    def __init__(self, config, n_routed_experts: int):
        """Initialize expert engine.

        Args:
            config: Model configuration
            n_routed_experts: Number of routed experts (excludes shared expert if present)
        """
        super().__init__()
        self.config = config
        self.n_routed_experts = n_routed_experts

        # Router: maps tokens to expert logits
        self.router = nn.Linear(config.n_embd, n_routed_experts, bias=False)

        # Expert weights (2-layer MLP, nanochat style: no bias, ReLU²)
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(n_routed_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(n_routed_experts)
        ])

        # Cutoff tracking for threshold mode
        # cutoff_ema_raw: EMA buffer of top-k cutoffs (min logit among selected tokens per expert)
        self.register_buffer('cutoff_ema_raw', torch.zeros(n_routed_experts))
        # Number of EMA updates applied (for bias correction in threshold mode)
        self.register_buffer('cutoff_ema_updates', torch.zeros(1, dtype=torch.long))
        
        # Accumulators for cutoff statistics (sum and count)
        # Persistent=False to exclude from state_dict but handle device placement
        self.register_buffer('cutoff_accum_sum', torch.zeros(n_routed_experts), persistent=False)
        self.register_buffer('cutoff_accum_count', torch.zeros(1, dtype=torch.long), persistent=False)

        # Initialize weights (called in __init__ for standalone usage)
        # Will be overridden by BaseGPT.init_weights() if used in full model
        self._init_engine_weights()

    @property
    def cutoff_ema(self) -> Tensor:
        """Effective (bias-corrected) cutoff used by threshold routing."""
        return self._effective_cutoff()

    def forward_topk(
        self,
        x: Tensor,
        layer_idx: int = 0,
        is_shared: bool = False
    ) -> Tuple[Tensor, Tensor, Tensor, Tensor, Optional[Tensor], Dict[str, Tensor]]:
        """Top-k routing forward pass.

        Each expert selects exactly k tokens via top-k selection on router logits.
        This provides perfect load balancing and is differentiable for training.

        Args:
            x: Input tensor (B, T, C)
            layer_idx: Layer index for metrics
            is_shared: Whether a shared expert exists (affects k computation only)

        Returns:
            h_flat: Expert outputs (total_active, C) UNWEIGHTED
            indices_flat: Token indices (total_active,) - flat, 1D
            weights_flat: UNNORMALIZED weights (total_active,) - caller divides by fanout or fanout+1
            fanout: Per-token expert count (N,) - caller uses for normalization
            shared_weights: (B*T,) or None - for softmax_e variants, shared expert weights
            metrics: Dictionary of routing metrics
        """
        B, T, C = x.shape
        n_tokens = B * T

        # Flatten input
        x_flat = x.view(-1, C)  # (B*T, C)

        # Router logits (cast to fp32 for numerical stability in subsequent ops)
        router_logits = self.router(x).float()  # (B, T, n_routed_experts) in fp32
        router_logits_flat = router_logits.view(-1, self.n_routed_experts)  # (B*T, n_routed_experts)

        # Apply activation to ALL logits BEFORE top-k
        # Returns (all_weights, shared_weights) - shared_weights is None for non-softmax_e
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity
        )

        # Top-k selection
        # Compute k based on formula (depends on is_shared)
        if is_shared:
            # GEC_shared: k = n_tokens × (G-1) / (G×E)
            G = self.config.granularity
            E = self.config.expansion
            k = int(n_tokens * (G - 1) // (G * E))
        else:
            # GEC: k = n_tokens / E
            k = int(n_tokens // self.config.expansion)

        k = min(k, n_tokens)  # Clamp to available tokens

        # Top-k selection on RAW logits (not activated weights)
        topk_values, topk_indices = torch.topk(
            router_logits_flat.t(),  # (n_routed_experts, B*T)
            k=k,
            dim=1
        )  # Both: (n_routed_experts, k)

        # Extract cutoffs (min logit per expert for EMA tracking)
        cutoffs = topk_values[:, -1]  # (n_routed_experts,)

        # Accumulate cutoffs for EMA update at step boundary
        if self.training:
            # Accumulate sum and count (in-place to avoid graph breaks)
            self.cutoff_accum_sum.add_(cutoffs.detach())
            self.cutoff_accum_count.add_(1)

        # Flatten to permutation indices
        indices_batched = topk_indices  # (n_routed_experts, k) - for BMM
        indices_flat = indices_batched.reshape(-1)  # (n_routed_experts * k,) - for return

        # Gather pre-computed weights at selected positions
        # all_weights.t(): (n_routed_experts, B*T)
        # topk_indices: (n_routed_experts, k)
        # Result: (n_routed_experts, k) -> flatten to (n_routed_experts * k,)
        weights_flat = torch.gather(all_weights.t(), dim=1, index=topk_indices).view(-1)

        # Compute fanout (count of experts per token) in fp32
        fanout = compute_fanout(n_tokens, indices_flat, x.device, torch.float32)  # (n_tokens,)

        # Expert computation (returns UNWEIGHTED outputs)
        h_flat = self._compute_expert_outputs(
            x_flat=x_flat,
            indices_batched=indices_batched,
        )  # (E*k, C) unweighted

        # Compute metrics
        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            indices=indices_flat,
            weights=weights_flat,
            fanout=fanout,
            cutoffs=cutoffs,
            n_tokens=n_tokens,
            layer_idx=layer_idx,
            k_actual=None,  # topk has fixed k, no capacity tracking
            above_counts=None,
            capacity_config=None,
            cutoff_ema_for_metrics=self._effective_cutoff(),
        )

        return h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics

    def forward_threshold(
        self,
        x: Tensor,
        layer_idx: int = 0,
        is_shared: bool = False
    ) -> Tuple[Tensor, Tensor, Tensor, Tensor, Optional[Tensor], Dict[str, Tensor]]:
        """Threshold routing forward pass with optional capacity constraints.

        Training mode:
            1. Top-k (no_grad) to extract cutoffs for EMA updates
            2. Capacity-bounded threshold routing (with gradients) for actual computation
               - Each expert processes k ∈ [k_min, k_max] tokens
               - Vectorized selection and batched BMM (no loops for computation!)

        Eval mode:
            - Pure threshold routing (no capacity constraints, no top-k overhead)

        This implementation follows shared_capacity_batched.py pattern:
        - Single batched BMM instead of for-loops
        - Dynamic padding to actual_k_max (not theoretical k_max)
        - Vectorized capacity-bounded selection

        Args:
            x: Input tensor (B, T, C)
            layer_idx: Layer index for metrics
            is_shared: Whether a shared expert exists

        Returns:
            h_flat: Expert outputs (total_active, C) UNWEIGHTED (or empty if no experts activated)
            indices_flat: Token indices (total_active,) - flat, 1D
            weights_flat: UNNORMALIZED weights (total_active,) - only valid entries
            fanout: Per-token expert count (N,) - caller uses for normalization
            shared_weights: (B*T,) or None - for softmax_e variants, shared expert weights
            metrics: Dictionary of routing metrics
        """
        B, T, C = x.shape
        n_tokens = B * T

        # Flatten input
        x_flat = x.view(-1, C)  # (B*T, C)

        # Router logits (cast to fp32)
        router_logits = self.router(x).float()
        router_logits_flat = router_logits.view(-1, self.n_routed_experts)

        # Apply activation to ALL logits BEFORE selection
        # Returns (all_weights, shared_weights) - shared_weights is None for non-softmax_e
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity
        )

        # Training mode - update cutoffs via top-k
        capacity_config = None
        topk_results = None
        if self.training:
            # Compute k for capacity bounds (same formula as forward_topk)
            if is_shared:
                G = self.config.granularity
                E = self.config.expansion
                k_target = int(n_tokens * (G - 1) // (G * E))
            else:
                k_target = int(n_tokens // self.config.expansion)

            # Capacity constraints (if enabled)
            if self.config.expert_capacity_factor >= 0:
                k_min = int(k_target * (1 - self.config.expert_capacity_factor))
                k_max = int(k_target * (1 + self.config.expert_capacity_factor))
                capacity_config = {'k_min': k_min, 'k_max': k_max}

                # OPTIMIZATION: Run single topk(k_max) to serve both cutoff extraction and selection
                with torch.no_grad():
                    topk_values, topk_indices = torch.topk(
                        router_logits_flat.t(),
                        k=min(k_max, n_tokens),
                        dim=1,
                        sorted=True  # Explicit: we need sorted results
                    )  # Both: (n_routed_experts, k_max)

                    # Extract cutoffs from k_target position (for EMA)
                    k_target_idx = min(k_target - 1, topk_values.shape[1] - 1)
                    cutoffs = topk_values[:, k_target_idx]  # (n_routed_experts,)

                    # Store for reuse in _threshold_selection
                    topk_results = {'values': topk_values, 'indices': topk_indices}

                    # Accumulate for EMA update
                    self.cutoff_accum_sum.add_(cutoffs.detach())
                    self.cutoff_accum_count.add_(1)
            else:
                # No capacity: run standard topk(k_target) for cutoff extraction only
                with torch.no_grad():
                    topk_values, _ = torch.topk(
                        router_logits_flat.t(),
                        k=min(k_target, n_tokens),
                        dim=1
                    )
                    cutoffs = topk_values[:, -1]  # (n_routed_experts,)

                    # Accumulate for EMA update
                    self.cutoff_accum_sum.add_(cutoffs.detach())
                    self.cutoff_accum_count.add_(1)

        # Threshold selection (vectorized, capacity-aware)
        effective_cutoff = self._effective_cutoff()
        selection_result = self._threshold_selection(
            router_logits_flat=router_logits_flat,
            all_weights=all_weights,
            x_flat=x_flat,
            cutoff_values=effective_cutoff,
            capacity_config=capacity_config,
            topk_results=topk_results
        )

        if selection_result is None:
            # No experts activated - return empty tensors
            h_flat = torch.zeros(0, C, device=x.device, dtype=x.dtype)
            indices_flat = torch.zeros(0, device=x.device, dtype=torch.long)
            weights_flat = torch.zeros(0, device=x.device, dtype=x.dtype)

            # Fanout is 0 for all tokens (no experts activated)
            fanout = torch.zeros(n_tokens, device=x.device, dtype=torch.float32)

            metrics = self._compute_metrics(
                router_logits_flat=router_logits_flat,
                indices=indices_flat,
                weights=weights_flat,
                fanout=fanout,
                cutoffs=effective_cutoff,
                n_tokens=n_tokens,
                layer_idx=layer_idx,
                k_actual=torch.zeros(self.n_routed_experts, device=x.device),
                above_counts=torch.zeros(self.n_routed_experts, device=x.device),
                capacity_config=capacity_config,
                cutoff_ema_for_metrics=effective_cutoff
            )

            return h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics

        indices_batched, weights_batched, valid_mask, k_actual, above_counts = selection_result

        # Flatten indices for fanout (only valid entries)
        indices_flat = indices_batched[valid_mask]  # (total_active,)
        weights_flat = weights_batched[valid_mask]  # (total_active,)

        # Compute fanout (count of experts per token) in fp32
        fanout = compute_fanout(n_tokens, indices_flat, x.device, torch.float32)  # (n_tokens,)

        # Expert computation (returns UNWEIGHTED outputs) - uses batched format internally
        h_batched = self._compute_expert_outputs(
            x_flat=x_flat,
            indices_batched=indices_batched,
        )  # (E*k_max, C) unweighted, includes padding

        # Extract only valid entries (flatten and mask)
        h_flat = h_batched[valid_mask.view(-1)]  # (total_active, C)

        # Compute metrics
        # Get instant cutoffs (from training topk or use EMA for eval)
        if self.training and self.cutoff_accum_count.item() > 0:
            # Estimate instant cutoff from current accumulation (approximate)
            instant_cutoffs = self.cutoff_accum_sum / self.cutoff_accum_count
        else:
            instant_cutoffs = effective_cutoff

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            indices=indices_flat,
            weights=weights_flat,
            fanout=fanout,
            cutoffs=instant_cutoffs,
            n_tokens=n_tokens,
            layer_idx=layer_idx,
            k_actual=k_actual,
            above_counts=above_counts,
            capacity_config=capacity_config,
            cutoff_ema_for_metrics=effective_cutoff
        )

        return h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics

    def _batched_expert_forward(self, x_batched: Tensor) -> Tensor:
        """Batched expert MLP forward pass (nanochat style: no bias, ReLU²).

        Args:
            x_batched: (n_routed_experts, k, C)

        Returns:
            h: (n_routed_experts, k, C)
        """
        # Stack 2D parameters to 3D
        weight1_3d = torch.stack([w for w in self.expert_weight1])  # (n_routed_experts, expert_dim, C)
        weight2_3d = torch.stack([w for w in self.expert_weight2])  # (n_routed_experts, C, expert_dim)

        # First layer: x @ W1^T
        h = torch.bmm(x_batched, weight1_3d.transpose(1, 2))  # (n_routed_experts, k, expert_dim)

        # Activation: ReLU²
        h = F.relu(h).square()

        # Second layer: h @ W2^T
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (n_routed_experts, k, C)

        return h

    def _threshold_selection(
        self,
        router_logits_flat: Tensor,
        all_weights: Optional[Tensor],
        x_flat: Tensor,
        cutoff_values: Tensor,
        capacity_config: dict = None,
        topk_results: dict = None
    ) -> Optional[Tuple[Tensor, Tensor, Tensor, Tensor, Tensor]]:
        """Vectorized threshold-based token selection with optional capacity constraints.

        This implements the fast batched selection pattern from shared_capacity_batched.py:
        - Vectorized capacity-bounded selection (no loops!)
        - Dynamic padding to actual_k_max
        - Minimal CPU-GPU syncs (batch conversion of k_actual to CPU)
        - OPTIMIZED: Reuses precomputed topk results when available

        Args:
            router_logits_flat: (n_tokens, n_routed_experts)
            all_weights: (n_tokens, n_routed_experts) or None - pre-computed activated weights
            x_flat: (n_tokens, C)
            cutoff_values: (n_routed_experts,) threshold values used for activation
            capacity_config: Optional dict with 'k_min', 'k_max' for capacity constraints
            topk_results: Optional dict with precomputed 'values' and 'indices' from topk(k_max)
                         Shape: (n_routed_experts, k_max)

        Returns:
            If any experts activate:
                indices_batched: (n_routed_experts, actual_k_max)
                weights_batched: (n_routed_experts, actual_k_max)
                valid_mask: (n_routed_experts, actual_k_max) - marks valid (non-padding) entries
                k_actual: (n_routed_experts,) - actual token count per expert
                above_counts: (n_routed_experts,) - tokens above threshold per expert
            If no experts activate:
                None
        """
        n_tokens, n_routed_experts = router_logits_flat.shape

        # Vectorized capacity-bounded selection
        # Compute above-threshold mask for all experts at once
        above_mask = router_logits_flat >= cutoff_values.unsqueeze(0)  # (n_tokens, n_routed_experts)
        above_counts = above_mask.sum(dim=0)  # (n_routed_experts,)

        if capacity_config is not None:
            # TRAINING WITH CAPACITY: Vectorized clamping
            k_min = capacity_config['k_min']
            k_max = capacity_config['k_max']
            k_actual = torch.clamp(above_counts, k_min, k_max)  # (n_routed_experts,)

            # Determine which experts need topk (hit bounds)
            needs_topk = (above_counts != k_actual)
        else:
            # PURE THRESHOLD: No capacity constraints
            k_actual = above_counts  # (n_routed_experts,)
            needs_topk = torch.zeros(n_routed_experts, dtype=torch.bool, device=x_flat.device)

        # Compute actual_k_max for padding (max tokens across all experts)
        # EXCEPTION: .item() required for tensor allocation (sync unavoidable)
        actual_k_max = int(k_actual.max().item())

        if actual_k_max == 0:
            return None  # No experts activated

        # Select tokens for each expert
        # Pre-allocate batched arrays (no x_batched - that's done in _scatter_expert)
        indices_batched = torch.zeros(n_routed_experts, actual_k_max, device=x_flat.device, dtype=torch.long)
        weights_batched = torch.zeros(n_routed_experts, actual_k_max, device=x_flat.device, dtype=x_flat.dtype)
        valid_mask = torch.zeros(n_routed_experts, actual_k_max, device=x_flat.device, dtype=torch.bool)

        # Batch convert k_actual to CPU (single sync instead of n_routed_experts syncs)
        k_actual_cpu = k_actual.cpu()

        # Process each expert (unavoidable loop for topk/selection, but minimal work)
        for expert_idx in range(n_routed_experts):
            k = int(k_actual_cpu[expert_idx])  # No sync - already on CPU
            if k == 0:
                continue

            if needs_topk[expert_idx]:
                # Hit capacity bounds
                if topk_results is not None:
                    # OPTIMIZED: Reuse precomputed topk(k_max) results (sorted, descending)
                    # Take first k entries (highest logit tokens)
                    active_indices = topk_results['indices'][expert_idx, :k]
                else:
                    # Fallback: compute topk on-the-fly
                    _, active_indices = torch.topk(
                        router_logits_flat[:, expert_idx],
                        k=k
                    )
            else:
                # Within bounds - use threshold mask
                active_indices = above_mask[:, expert_idx].nonzero(as_tuple=False).squeeze(-1)

            # Fill batched arrays
            indices_batched[expert_idx, :k] = active_indices
            # Gather pre-computed weights at selected positions
            weights_batched[expert_idx, :k] = all_weights[active_indices, expert_idx]
            valid_mask[expert_idx, :k] = True

        return indices_batched, weights_batched, valid_mask, k_actual, above_counts

    def _compute_expert_outputs(
        self,
        x_flat: Tensor,
        indices_batched: Tensor,
    ) -> Tensor:
        """Gather tokens, run expert forward. Returns UNWEIGHTED outputs.

        Weights are applied during scatter (fused operation). This allows scatter
        backends to fuse weight multiplication with the scatter loop.

        Args:
            x_flat: Input tokens (n_tokens, C)
            indices_batched: Token indices per expert (n_routed_experts, k)

        Returns:
            h_flat: Expert outputs (E*k, C) UNWEIGHTED, ready for weighted scatter
        """
        # Gather selected tokens
        x_batched = x_flat[indices_batched]  # (n_routed_experts, k, C)

        # Batched expert forward
        h = self._batched_expert_forward(x_batched)  # (n_routed_experts, k, C)

        # Flatten to (E*k, C) for scatter - NO weight application here
        h_flat = h.view(-1, h.shape[-1])

        return h_flat

    def _compute_metrics(
        self,
        router_logits_flat: Tensor,
        indices: Tensor,
        weights: Tensor,
        fanout: Tensor,
        cutoffs: Tensor,
        n_tokens: int,
        layer_idx: int,
        k_actual: Tensor = None,
        above_counts: Tensor = None,
        capacity_config: dict = None,
        cutoff_ema_for_metrics: Optional[Tensor] = None
    ) -> Dict[str, Tensor]:
        """Compute routing metrics.

        Args:
            router_logits_flat: (n_tokens, n_routed_experts)
            indices: Flattened token indices (total_active,)
            weights: Flattened weights (total_active,)
            fanout: Per-token expert count (n_tokens,)
            cutoffs: Instant cutoffs (n_routed_experts,)
            n_tokens: Total tokens
            layer_idx: Layer index
            k_actual: Actual tokens per expert (for capacity tracking)
            above_counts: Tokens above threshold (for capacity tracking)
            capacity_config: Capacity constraints (for metrics)

        Returns:
            Dictionary of routing metrics
        """
        # Use fanout directly (already computed)
        token_fanout = fanout

        # Expert token counts
        if k_actual is not None:
            expert_token_counts = k_actual.float()
        else:
            # Top-k mode: uniform k per expert
            k_per_expert = len(indices) // self.n_routed_experts if self.n_routed_experts > 0 else 0
            expert_token_counts = torch.full((self.n_routed_experts,), k_per_expert,
                                            dtype=torch.float32, device=indices.device)

        # Expert usage (fraction of tokens processed)
        expert_usage = expert_token_counts / n_tokens

        # Import here to avoid circular dependency
        from ...utils import compute_routing_metrics

        cutoff_ema_metric = cutoff_ema_for_metrics if cutoff_ema_for_metrics is not None else self._effective_cutoff()

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,
            cutoff_ema=cutoff_ema_metric.clone(),
            weights=weights,
            router_logits_flat=router_logits_flat,
            token_fanout=token_fanout,
            expert_usage=expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=fanout,  # Pass fanout as normalizer for metrics (caller adds +1 for shared)
            indices=indices,
            above_counts=above_counts if capacity_config else None,
            k_min=capacity_config['k_min'] if capacity_config else None,
            k_max=capacity_config['k_max'] if capacity_config else None,
        )

        return metrics

    def _effective_cutoff(self) -> Tensor:
        """Return cutoff EMA used for threshold routing (bias-corrected when available)."""
        updates = int(self.cutoff_ema_updates.item())
        if updates <= 0:
            return self.cutoff_ema_raw

        alpha = float(self.config.cutoff_ema_alpha)
        denom = 1.0 - (alpha ** updates)
        if denom <= 0.0:
            return self.cutoff_ema_raw
        return self.cutoff_ema_raw / denom

    def finalize_cutoff_accumulation(self, apply_update: bool = True):
        """Finalize cutoff accumulation at training step boundary.

        Computes arithmetic mean of accumulated topk cutoffs from all micro-batches
        in the current step, then updates the cutoff EMA with this mean.

        This should be called once per training step, after all gradient accumulation
        micro-batches complete (via BaseGPT.step_complete()).

        Note: This is a no-op if no cutoffs were accumulated (e.g., during eval or topk mode).
        """
        if self.cutoff_accum_count.item() > 0:
            if apply_update:
                # Compute arithmetic mean across micro-batches: [n_routed_experts]
                cutoff_mean = self.cutoff_accum_sum / self.cutoff_accum_count

                # EMA update
                alpha = self.config.cutoff_ema_alpha
                self.cutoff_ema_raw.mul_(alpha).add_(cutoff_mean, alpha=1 - alpha)
                self.cutoff_ema_updates.add_(1)

            # Clear accumulators for next step
            self.cutoff_accum_sum.zero_()
            self.cutoff_accum_count.zero_()

    def sync_cutoff_state(self) -> Tensor:
        """Return raw cutoff EMA buffer for syncing across GPUs.

        Returns:
            cutoff_ema_raw: (n_routed_experts,) tensor to be synced
        """
        return self.cutoff_ema_raw

    def _init_engine_weights(self):
        """Initialize expert and router weights.

        Simple Xavier uniform initialization for standalone usage.
        Will be overridden by BaseGPT.init_weights() if used in full model.
        """
        # Initialize router
        nn.init.xavier_uniform_(self.router.weight)

        # Initialize expert weights
        for w in self.expert_weight1:
            nn.init.xavier_uniform_(w)
        for w in self.expert_weight2:
            nn.init.xavier_uniform_(w)
