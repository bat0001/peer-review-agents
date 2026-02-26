"""
Manual Implementation of Expert Parallelism Engine. 

It should have the same purpose of engine.py
"""

from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

import torch.distributed as dist

from ..router_utils import apply_router_activation, compute_fanout

from ...ops.all_to_all import all_to_all
from ...ops.prealloc_all_to_all import prealloc_all_to_all

class ParallelExperts(nn.Module):
    def __init__(self, config, n_routed_experts: int):
        """
        Initialize the ParallelExperts module.

        Note, we only initialize the weights of the experts of the current process.

        E.g., 
        - World size: 8
        - Expansion: 8
        - Granularity: 2
        - Each process owns 8*2/8 = 2 experts
        - We only initialize the weights of the experts of the current process, i.e. [rank*2 + 0, rank*2 + 1]

        Args:
            config: Model configuration
            n_routed_experts: Number of routed experts (excludes shared expert if present)
        """
        super().__init__()
        self.config = config
        self.n_routed_experts = n_routed_experts
        if not dist.is_initialized():
            raise RuntimeError(
                "Expert parallelism requires torch.distributed to be initialized (use torchrun)."
            )
        self.world_size = dist.get_world_size()
        self.rank = dist.get_rank()
        if n_routed_experts % self.world_size != 0:
            raise ValueError(
                f"n_routed_experts ({n_routed_experts}) must be divisible by world_size ({self.world_size}) for EP"
            )
        self.local_experts = n_routed_experts // self.world_size
        self.local_expert_ids = torch.arange(self.local_experts) + self.rank * self.local_experts

        # Router still DP
        self.router = nn.Linear(config.n_embd, n_routed_experts, bias=False)

        # Expert weights (2-layer MLP, nanochat style: no bias, ReLU²). EP only.
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(self.local_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(self.local_experts)
        ])

        self.register_buffer('cutoff_ema_raw', torch.zeros(n_routed_experts)) # Raw EMA buffer for ALL experts
        self.register_buffer('cutoff_ema_updates', torch.zeros(1, dtype=torch.long))  # Number of EMA updates applied
        self.register_buffer('cutoff_accum_sum', torch.zeros(n_routed_experts), persistent=False) # Accumulator for cutoff statistics for ALL experts
        self.register_buffer('cutoff_accum_count', torch.zeros(1, dtype=torch.long), persistent=False) # Accumulator for cutoff statistics

        self._init_engine_weights()

    @property
    def cutoff_ema(self) -> Tensor:
        """Effective (bias-corrected) cutoff used by threshold routing."""
        return self._effective_cutoff()



    def forward_topk(self, x: Tensor, layer_idx: int = 0, is_shared: bool = False) -> Tuple[Tensor, Tensor, Tensor, Tensor, Optional[Tensor], Dict[str, Tensor]]:
        """
        Top-k routing forward pass with Expert Parallelism.

        Step 1: Logits computation
        Step 2: We first all gather the router logits for all experts, so each rank knows exactly how every rank works and how every token within the global batch is routed.
        Step 3: Then, we can perform top-k selection on the global router logits
        Step 4: Then, we can calculate the communication indices, input_split_counts, output_split_counts, etc.
        Step 5: All-to-all dispatch - send tokens to the appropriate ranks.
        Step 6: expert forward pass (bmm)
        Step 7: All-to-all combine - send expert outputs back to the original ranks.
        Afterwards, we return the expert outputs, which the model wrapper will then scatter to the token indices.

        Since we are doing EP, we can support a much higher batch size for each expert, which helps with load balancing.

        Args:
            x: (B, T, C)
            layer_idx: Layer index
            is_shared: Whether the expert is shared

        Returns:
            h_flat: (total_active, C) UNWEIGHTED expert outputs
            indices_flat: (total_active,) token indices - flat, 1D (LOCAL to this rank's batch)
            weights_flat: (total_active,) UNNORMALIZED routed weights
            fanout: (N,) per-token expert count for normalization
            shared_weights: (B*T,) or None - for softmax_e variants, shared expert weights
            metrics: routing stats
        """
        B, T, C = x.shape
        n_tokens = B * T
        global_tokens = n_tokens * self.world_size

        # Flatten input
        x_flat = x.view(-1, C)  # (B*T, C)

        # Step 1: Router logits computation
        router_logits = self.router(x).float()  # (B, T, n_routed_experts) in fp32
        router_logits_flat = router_logits.view(-1, self.n_routed_experts)  # (B*T, n_routed_experts)

        # Apply activation to ALL logits BEFORE selection
        # Returns (all_weights, shared_weights) - shared_weights is None for non-softmax_e
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity
        )

        # Step 2: All-gather router logits across all ranks (no grad - discrete routing)
        with torch.no_grad():
            global_router_logits = torch.empty(
                (self.world_size * n_tokens, self.n_routed_experts),
                device=router_logits_flat.device, dtype=router_logits_flat.dtype
            )
            dist.all_gather_into_tensor(global_router_logits, router_logits_flat)

        # Step 3: Global top-k selection
        if is_shared:
            G = self.config.granularity
            E = self.config.expansion
            k = int(n_tokens * (G - 1) // (G * E))
        else:
            k = int(n_tokens // self.config.expansion)

        k = min(k, n_tokens)
        k_global = k * self.world_size

        topk_values, topk_indices = torch.topk(
            global_router_logits.t(),  # (n_routed_experts, B*T*world_size)
            k=k_global,
            dim=1,
            sorted=True,
        )

        # Extract cutoffs for EMA tracking
        cutoffs = topk_values[:, -1]
        if self.training:
            self.cutoff_accum_sum.add_(cutoffs.detach())
            self.cutoff_accum_count.add_(1)

        # Alternative plan: we all-to-all by local experts.

        expert_starts = self.local_experts * self.rank

        input_splits_sizes, output_splits_sizes = [], []
        # Metadata accumulators for reconstruction
        all_send_indices = []
        all_expert_ids = []
        x_list = []  # Tokens to send for each local expert

        for i in range(self.local_experts):
            # the i-th experts on all ranks
            these_experts_indices = topk_indices[i::self.local_experts]

            local_mask = ((these_experts_indices >= self.rank * n_tokens) & (these_experts_indices < (self.rank + 1) * n_tokens))
            send_indices = these_experts_indices[local_mask]

            # Track metadata
            all_send_indices.append(send_indices % n_tokens)
            # Expert IDs: tokens go to different experts on different ranks
            # local_mask[r] selects tokens going to rank r's i-th local expert (global ID: i + r*local_experts)
            expert_ids_per_rank = torch.arange(self.world_size, device=topk_indices.device) * self.local_experts + i
            expert_ids_for_send = expert_ids_per_rank.unsqueeze(1).expand_as(local_mask)[local_mask]
            all_expert_ids.append(expert_ids_for_send)

            my_expert_indices = topk_indices[i+expert_starts] # B_i to E_{i+rank*local_experts}, e.g. E0 for rank 0 at i=0

            output_splits_sizes.append([
                ((my_expert_indices >= r * n_tokens) & (my_expert_indices < (r + 1) * n_tokens)).sum().item()
                for r in range(self.world_size)
            ])
            input_splits_sizes.append([
                local_mask[r].sum().item()
                for r in range(self.world_size)
            ])
            tokens_to_send = x_flat[send_indices % n_tokens].contiguous()
            x_list.append(tokens_to_send)

        # Step 5: Dispatch - all-to-all to send tokens to experts
        # Top-k: each expert receives exactly k_global tokens, use packed mode
        tokens_received_flat = prealloc_all_to_all(
            x_list,
            output_splits_sizes,
            input_splits_sizes,
            hidden_size=C,
            device=x.device,
            dtype=x.dtype,
            recv_offsets=None,  # Packed
        )
        tokens_received = tokens_received_flat.view(self.local_experts, k_global, C)

        # Step 6: Expert forward pass
        h = self._batched_expert_forward(tokens_received)

        # Step 7: Combine - all-to-all to send expert outputs back
        # h[i] has k_global tokens, we send all of them back (top-k = uniform per expert)
        h_list = [h[i] for i in range(self.local_experts)]
        expert_outputs_received = prealloc_all_to_all(
            h_list,
            input_splits_sizes,   # Swapped: what we sent becomes what we receive
            output_splits_sizes,  # Swapped
            hidden_size=C,
            device=h.device,
            dtype=h.dtype,
            recv_offsets=None,  # Packed
        )

        # Step 8: Compute weights and return

        # Reconstruct full batch metadata
        local_indices = torch.cat(all_send_indices, dim=0)
        # Note: We need expert_ids relative to 0..n_routed_experts for looking up logits
        expert_ids = torch.cat(all_expert_ids, dim=0)

        # Gather pre-computed weights at selected positions
        weights_flat = all_weights[local_indices, expert_ids]

        fanout = compute_fanout(n_tokens, local_indices, x.device, torch.float32)

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            indices=local_indices,
            weights=weights_flat,
            fanout=fanout,
            cutoffs=cutoffs,
            n_tokens=global_tokens,
            layer_idx=layer_idx,
            cutoff_ema_for_metrics=self._effective_cutoff(),
        )

        return expert_outputs_received, local_indices, weights_flat, fanout, shared_weights, metrics

    def forward_threshold(self, x: Tensor, layer_idx: int = 0, is_shared: bool = False) -> Tuple[Tensor, Tensor, Tensor, Tensor, Optional[Tensor], Dict[str, Tensor]]:
        """Threshold routing forward pass with Expert Parallelism.

        Uses threshold-based routing where each expert processes tokens above its EMA cutoff.
        Variable k per expert requires padding for BMM.

        Args:
            x: (B, T, C)
            layer_idx: Layer index
            is_shared: Whether the expert is shared

        Returns:
            h_flat: (total_active, C) UNWEIGHTED expert outputs
            indices_flat: (total_active,) token indices - flat, 1D (LOCAL to this rank's batch)
            weights_flat: (total_active,) UNNORMALIZED routed weights
            fanout: (N,) per-token expert count for normalization
            shared_weights: (B*T,) or None - for softmax_e variants, shared expert weights
            metrics: routing stats
        """
        B, T, C = x.shape
        n_tokens = B * T
        global_tokens = n_tokens * self.world_size

        if is_shared:
            G = self.config.granularity
            E = self.config.expansion
            k = int(n_tokens * (G - 1) // (G * E))
        else:
            k = int(n_tokens // self.config.expansion)

        k = min(k, n_tokens)
        k_global = k * self.world_size

        # Step 1: Router logits computation
        router_logits = self.router(x).float()  # (B, T, n_routed_experts)
        router_logits_flat = router_logits.view(-1, self.n_routed_experts)  # (B*T, n_routed_experts)

        # Apply activation to ALL logits BEFORE selection
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity
        )

        # Step 2: All-gather router logits across all ranks
        with torch.no_grad():
            global_router_logits = torch.empty(
                (global_tokens, self.n_routed_experts),
                device=router_logits_flat.device, dtype=router_logits_flat.dtype
            )
            dist.all_gather_into_tensor(global_router_logits, router_logits_flat)

        # Step 3: Threshold routing - compute per-expert indices as List[Tensor]
        effective_cutoff = self._effective_cutoff()
        above_mask = global_router_logits >= effective_cutoff.unsqueeze(0)
        above_counts = above_mask.sum(dim=0)

        capacity_config = None
        if self.training:

            if self.config.expert_capacity_factor >= 0:
                k_min = int(k_global * (1 - self.config.expert_capacity_factor))
                k_max = int(k_global * (1 + self.config.expert_capacity_factor))
                capacity_config = {'k_min': k_min, 'k_max': k_max}

                with torch.no_grad():
                    topk_values, topk_indices = torch.topk(
                        global_router_logits.t(),
                        k=k_max,
                        dim=1,
                        sorted=True,
                    )
                    cutoffs = topk_values[:, k_global - 1]
                

                k_actual = torch.clamp(above_counts, k_min, k_max)
                indices_list = [topk_indices[i, :int(k_actual[i].item())] for i in range(self.n_routed_experts)]
            
            else: # no capacity
                k_actual = above_counts

                with torch.no_grad():
                    topk_values, topk_indices = torch.topk(
                        global_router_logits.t(),
                        k=k_global,
                        dim=1,
                        sorted=True,
                    )
                    cutoffs = topk_values[:, -1]
                
                indices_list = [torch.nonzero(above_mask[:, i], as_tuple=True)[0] for i in range(self.n_routed_experts)]
            
            self.cutoff_accum_sum.add_(cutoffs.detach())
            self.cutoff_accum_count.add_(1)

            

        else: # inference only
            # Create a list where indices_list[i] contains the token indices for expert i
            indices_list = [torch.nonzero(above_mask[:, i], as_tuple=True)[0] for i in range(self.n_routed_experts)]
            cutoffs = effective_cutoff
            k_actual = above_counts  # No capacity constraints during inference

        # Step 4: Compute dispatch metadata
        x_flat = x.view(-1, C)

        input_splits_sizes, output_splits_sizes = [], []
        all_send_indices, x_list = [], []
        k_actual_local = []  # Tokens received by each local expert

        expert_starts = self.local_experts * self.rank

        for i in range(self.local_experts):

            remote_expert_indices = indices_list[i::self.local_experts]

            local_mask = [((remote_expert_indices[r] >= self.rank * n_tokens) & (remote_expert_indices[r] < (self.rank + 1) * n_tokens)) for r in range(self.world_size)] # List(Tensor(bool)): rank 0, i=0: [B0 -> E0, B0 -> E2, B0 -> E4, ...]
            send_indices = torch.cat([remote_expert_indices[r][local_mask[r]] for r in range(self.world_size)], dim=0) # (total sent tokens,)

            all_send_indices.append(send_indices % n_tokens)

            my_expert_indices = indices_list[i+expert_starts] # B_i to E_{i+rank*local_experts}, e.g. E0 for rank 0 at i=0

            output_splits_sizes.append([
                ((my_expert_indices >= r * n_tokens) & (my_expert_indices < (r + 1) * n_tokens)).sum().item()
                for r in range(self.world_size)
            ])
            input_splits_sizes.append([
                local_mask[r].sum().item()
                for r in range(self.world_size)
            ])

            k_actual_local.append(sum(output_splits_sizes[i]))

            tokens_to_send = x_flat[send_indices % n_tokens].contiguous()
            x_list.append(tokens_to_send)

        # Step 5: Dispatch with padding
        # Each local expert receives k_actual_local[i] tokens, but we pad to max of output_splits_sizes for BMM
        k_actual_max = max(k_actual_local) if k_actual_local else 0  # e.g., E0: 10k, E1: 11k, we pad to 11k
        recv_offsets = [i * k_actual_max for i in range(self.local_experts)]
        tokens_received_flat = prealloc_all_to_all(
            x_list,
            output_splits_sizes,
            input_splits_sizes,
            hidden_size=C,
            device=x.device,
            dtype=x.dtype,
            recv_offsets=recv_offsets,  # Padded mode (stride inferred from offsets)
        )
        tokens_received = tokens_received_flat.view(self.local_experts, k_actual_max, C) if k_actual_max > 0 else tokens_received_flat.view(self.local_experts, 0, C)

        # Step 6: Expert forward pass (BMM on padded input, padding = zeros)
        h = self._batched_expert_forward(tokens_received)

        # Step 7: Combine - slice to remove padding before sending back
        h_list = [h[i, :k_actual_local[i]] for i in range(self.local_experts)]
        expert_outputs_received = prealloc_all_to_all(
            h_list,
            input_splits_sizes,   # Swapped
            output_splits_sizes,  # Swapped
            hidden_size=C,
            device=h.device,
            dtype=h.dtype,
            recv_offsets=None,  # Packed
        )

        # Step 8: Compute weights and return
        local_indices = torch.cat(all_send_indices, dim=0)

        # Build expert_ids using repeat_interleave
        # Order: for each local expert i, iterate through all ranks r (E0, E2, E4, ..., E1, E3, E5, ...)
        counts = [input_splits_sizes[i][r]
                  for i in range(self.local_experts)
                  for r in range(self.world_size)]
        expert_ids_pattern = [r * self.local_experts + i
                              for i in range(self.local_experts)
                              for r in range(self.world_size)]
        counts_tensor = torch.tensor(counts, device=x.device)
        expert_ids = torch.tensor(expert_ids_pattern, device=x.device).repeat_interleave(counts_tensor)

        # Gather pre-computed weights at selected positions
        weights_flat = all_weights[local_indices, expert_ids]

        fanout = compute_fanout(n_tokens, local_indices, x.device, torch.float32)

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            indices=local_indices,
            weights=weights_flat,
            fanout=fanout,
            cutoffs=cutoffs,
            n_tokens=global_tokens,
            layer_idx=layer_idx,
            k_actual=k_actual,
            above_counts=above_counts,
            capacity_config=capacity_config,
            cutoff_ema_for_metrics=effective_cutoff,
        )

        return expert_outputs_received, local_indices, weights_flat, fanout, shared_weights, metrics


    def _batched_expert_forward(self, x_batched: Tensor) -> Tensor:
        """Batched expert MLP forward pass (nanochat style: no bias, ReLU²).

        Args:
            x_batched: (local_experts, k_global, C) with EP

        Returns:
            h: (local_experts, k_global, C)
        """
        # Stack 2D parameters to 3D
        weight1_3d = torch.stack([w for w in self.expert_weight1])  # (local_experts, expert_dim, C)
        weight2_3d = torch.stack([w for w in self.expert_weight2])  # (local_experts, C, expert_dim)

        # First layer: x @ W1^T
        h = torch.bmm(x_batched, weight1_3d.transpose(1, 2))  # (local_experts, k_global, expert_dim)

        # Activation: ReLU²
        h = F.relu(h).square()

        # Second layer: h @ W2^T
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (local_experts, k_global, C)

        return h

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
            n_tokens=n_tokens,  # Pass global token count for EP (above_counts is global)
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

        Note: With EP, we update ALL experts' cutoff EMA at once. I.e., this operation is repeated on every rank, and should have the exact same result since we synced the global router logits for all experts.
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
