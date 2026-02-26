"""Expert Choice (EC) MLP with configurable routing granularity."""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .model_base import BaseMLP, ModelConfig, RouterMixin
from ..utils import compute_routing_metrics


class ECMLP(BaseMLP, RouterMixin):
    """Expert Choice MLP with configurable routing granularity.

    This implementation extends GEC by allowing configurable top-k selection granularity:
    - routing_chunk_seqs=None: Global routing (standard GEC behavior)
    - routing_chunk_seqs=1: Per-sequence routing
    - routing_chunk_seqs=N: Per N-sequence routing

    Memory usage scales as O(n_experts * density * batch_size * seq_length).
    For example, with 4 experts and density=0.25, we process the same number
    of token-expert pairs as there are input tokens. With 8 experts and
    density=0.5, we process 4x as many token-expert pairs as input tokens.

    Key differences from standard MoE:
    - Experts select tokens (not tokens selecting experts)
    - Each expert processes exactly k = n_tokens * density tokens (per chunk)
    - Tokens can be selected by multiple experts (soft assignment)
    - Uses scatter_add for proper accumulation when tokens overlap
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        # Ensure required parameters are not None
        assert config.n_experts is not None, "n_experts must be specified for EC"
        assert config.expert_dim is not None, "expert_dim must be specified for EC"

        # Router layer (one per expert) - no bias! (nanochat style)
        self.router = nn.Linear(config.n_embd, config.n_experts, bias=False)

        # Expert parameters as ParameterList of 2D tensors (for per-expert optimizer states)
        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(config.n_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(config.n_experts)
        ])

        # No separate activation module - use ReLU² inline (nanochat style)

        # Moving average of cutoff values per expert
        self.register_buffer('cutoff_ema', torch.zeros(config.n_experts))
        self.ema_decay = 0.99  # EMA decay rate

        # Routing chunk configuration
        self.routing_chunk_seqs = config.routing_chunk_seqs

        # Representative layers for metrics tracking
        self.repr_layers = {0, config.n_layer//4, config.n_layer//2, 3*config.n_layer//4, config.n_layer-1}
        self.temporal_window = getattr(config, 'temporal_window', 100)
        self.temporal_warmup = getattr(config, 'temporal_warmup', 10)

        # Temporal buffers for representative layers
        for layer in self.repr_layers:
            self.register_buffer(f'cutoff_history_L{layer}', torch.zeros(self.temporal_window, config.n_experts))
            self.register_buffer(f'history_idx_L{layer}', torch.tensor(0))
            self.register_buffer(f'prev_cutoff_L{layer}', torch.zeros(config.n_experts))

    def _expert_forward(self, x: torch.Tensor, expert_idx: int) -> torch.Tensor:
        """Forward pass for a single expert (nanochat style: no bias, ReLU²)."""
        h = F.linear(x, self.expert_weight1[expert_idx])
        h = F.relu(h).square()  # ReLU² (nanochat style)
        h = F.linear(h, self.expert_weight2[expert_idx])
        return h

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Dispatcher: calls topk or threshold forward based on training mode."""
        if self.training:
            return self.forward_topk(x, layer_idx)
        else:
            return self.forward_threshold(x, layer_idx)

    def forward_topk(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with global top-k routing (perfect load balance)."""
        B, T, C = x.shape
        n_experts = self.config.n_experts

        # Validate routing chunk configuration
        if self.routing_chunk_seqs is not None:
            assert self.routing_chunk_seqs > 0, \
                f"routing_chunk_seqs must be positive, got {self.routing_chunk_seqs}"
            assert B % self.routing_chunk_seqs == 0, \
                f"Batch size {B} must be divisible by routing_chunk_seqs {self.routing_chunk_seqs}"
            assert self.routing_chunk_seqs <= B, \
                f"routing_chunk_seqs {self.routing_chunk_seqs} cannot exceed batch size {B}"

        # Compute routing scores for all tokens to all experts
        router_logits = self.router(x)  # (B, T, n_experts)

        # Flatten for global selection
        x_flat = x.view(-1, C)  # (B*T, C)
        router_logits_flat = router_logits.view(B, T, n_experts)  # Keep B,T separate for chunking

        # Determine chunking
        chunk_seqs = self.routing_chunk_seqs if self.routing_chunk_seqs is not None else B
        n_chunks = B // chunk_seqs
        chunk_size = chunk_seqs * T

        # Reshape for chunked processing
        # router_logits_chunked: (n_chunks, chunk_size, n_experts)
        router_logits_chunked = router_logits_flat.view(n_chunks, chunk_size, n_experts)

        # Compute k per chunk (compute-matching: each expert selects 1/E of chunk tokens)
        k = chunk_size // self.config.expansion
        assert k > 0, f"k must be positive (got {k} from chunk_size={chunk_size}, expansion={self.config.expansion})"
        assert k <= chunk_size, \
            f"k={k} exceeds chunk_size={chunk_size} (expansion={self.config.expansion})"

        # Select top-k tokens for ALL experts in parallel, per chunk (on raw logits)
        # Transpose to (n_chunks, n_experts, chunk_size) for per-expert top-k
        router_logits_for_topk = router_logits_chunked.transpose(1, 2)  # (n_chunks, n_experts, chunk_size)

        # Top-k per (chunk, expert)
        topk_values, topk_indices = torch.topk(
            router_logits_for_topk, k=min(k, chunk_size), dim=-1
        )  # (n_chunks, n_experts, k)

        # Get cutoff values per (chunk, expert)
        cutoffs = topk_values[:, :, -1] if k > 0 else torch.zeros(
            n_chunks, n_experts, device=x.device
        )  # (n_chunks, n_experts)

        # Update moving averages (average across chunks)
        with torch.no_grad():
            avg_cutoffs = cutoffs.mean(dim=0)  # (n_experts,)
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * avg_cutoffs  # type: ignore

        # Adjust indices to global token positions
        # For each chunk, add offset: chunk_idx * chunk_size
        chunk_offsets = torch.arange(n_chunks, device=x.device).view(n_chunks, 1, 1) * chunk_size
        global_topk_indices = topk_indices + chunk_offsets  # (n_chunks, n_experts, k)

        # Group selections per expert so the GEMMs match global-routing geometry
        # (n_experts, n_chunks, k)
        indices_per_expert = global_topk_indices.permute(1, 0, 2)
        values_per_expert = topk_values.permute(1, 0, 2)

        # Flatten chunk dimension while keeping experts grouped: (n_experts, n_chunks * k)
        indices_flat = indices_per_expert.reshape(n_experts, n_chunks * k)

        # Gather token representations for each expert
        tokens_for_expert = x_flat[indices_flat.reshape(-1)].view(n_experts, n_chunks * k, C)

        # Stack 2D parameters to 3D for batched computation
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        # First layer: x -> hidden (nanochat style: no bias, ReLU²)
        h = torch.bmm(tokens_for_expert, weight1_3d.transpose(1, 2))  # (n_experts, n_chunks * k, expert_dim)
        h = F.relu(h).square()  # ReLU² (nanochat style)

        # Second layer: hidden -> output (nanochat style: no bias)
        h = torch.bmm(h, weight2_3d.transpose(1, 2))  # (n_experts, n_chunks * k, C)

        # Apply soft weights from router (activate the selected logits)
        weights = self.apply_router_activation(values_per_expert, self.config.router_activation).reshape(n_experts, n_chunks * k, 1)

        # Prepare indices for normalization
        gathered_indices = indices_flat.reshape(-1)
        n_tokens = B * T

        # Reshape router_logits_chunked for metrics
        router_logits_flat_for_norm = router_logits_chunked.reshape(n_tokens, n_experts)

        # Compute fanout (no shared expert, so just fanout)
        fanout = self.compute_fanout(n_tokens, gathered_indices, x.device, x.dtype)  # (n_tokens,)

        # Normalize h BEFORE scatter (compile will fuse with scatter)
        # fanout[indices] is always >= 1 since selected tokens have at least 1 expert
        h = h * weights / fanout[gathered_indices].reshape(n_experts, n_chunks * k, 1)

        # Flatten back
        h = h.reshape(-1, C)  # (n_experts * n_chunks * k, C)

        # Scatter
        output = torch.zeros_like(x_flat)
        output.index_add_(0, gathered_indices, h)

        # Reshape back
        output = output.view(B, T, C)

        # Compute metrics using unified method
        token_fanout = torch.zeros(n_tokens, device=x.device)
        ones = torch.ones(len(gathered_indices), device=x.device)
        token_fanout.scatter_add_(0, gathered_indices, ones)

        # Count how many tokens each expert processed (across all chunks)
        expert_ids = torch.arange(n_experts, device=x.device).view(-1, 1).expand_as(indices_flat)
        expert_token_counts = torch.zeros(n_experts, device=x.device)
        expert_token_counts.scatter_add_(
            0,
            expert_ids.reshape(-1),
            torch.ones_like(expert_ids, dtype=torch.float32).reshape(-1),
        )
        expert_usage = expert_token_counts / n_tokens

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,  # (n_chunks, n_experts) - will be averaged in method
            cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
            weights=weights.reshape(-1),
            router_logits_flat=router_logits_flat_for_norm,
            token_fanout=token_fanout,
            expert_usage=expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=fanout,
            indices=gathered_indices,
        )

        # Add raw layer data for visualization (during eval only)
        if not self.training:
            metrics['layer_data'] = {
                'weights': weights.reshape(-1).detach(),
                'fanout': token_fanout.detach(),
                'cutoffs': cutoffs.mean(dim=0).detach() if cutoffs.ndim == 2 else cutoffs.detach(),
                'router_logits': router_logits_flat_for_norm.detach(),
            }

        return output, metrics

    def forward_threshold(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with learned threshold routing (causal, for autoregressive generation).

        Uses the averaged cutoff_ema learned during training (which averages across chunks).

        WARNING: No backward pass support. Use forward_topk() for training.
        """
        assert not torch.is_grad_enabled(), \
            "Threshold routing does not support backward pass. Use forward_topk() for training."

        B, T, C = x.shape
        n_experts = self.config.n_experts
        n_tokens = B * T

        # Compute routing scores for all tokens to all experts
        router_logits = self.router(x)  # (B, T, n_experts)

        # Flatten
        x_flat = x.view(-1, C)  # (B*T, C)
        router_logits_flat = router_logits.view(-1, n_experts)  # (B*T, n_experts)

        # Initialize output and counts
        output = torch.zeros_like(x_flat)
        counts = torch.zeros(n_tokens, device=x.device)

        # Loop through experts (causal - no future tokens needed)
        # Use cutoff_ema which was averaged across chunks during training
        for expert_idx in range(n_experts):
            # Which tokens activate this expert? (threshold-based)
            mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]  # type: ignore
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            # Process only active tokens with this expert
            x_active = x_flat[active_indices]
            h = self._expert_forward(x_active, expert_idx)

            # Apply router activation (use config setting)
            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx].unsqueeze(0),
                self.config.router_activation
            ).squeeze(0)

            # Accumulate
            output.index_add_(0, active_indices, h * weights.unsqueeze(-1))
            counts.index_add_(0, active_indices, torch.ones_like(active_indices, dtype=torch.float))

        # counts already represents fanout (how many experts activated per token)
        # Normalize by fanout (clamped to avoid div by 0 for unselected tokens)
        fanout = counts.clamp(min=1e-6)
        output = output / fanout.unsqueeze(-1)

        # Reshape back
        output = output.view(B, T, C)

        # Compute metrics
        avg_experts = counts.mean()
        expert_token_counts = torch.zeros(n_experts, device=x.device)
        for e in range(n_experts):
            scores_e = router_logits_flat[:, e]
            expert_token_counts[e] = (scores_e > self.cutoff_ema[e]).float().sum()  # type: ignore

        expert_usage = expert_token_counts / n_tokens

        # Use same metrics computation as training
        metrics = compute_routing_metrics(
            cutoffs=self.cutoff_ema.clone(),  # type: ignore
            cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
            weights=counts,
            router_logits_flat=router_logits_flat,
            token_fanout=counts,
            expert_usage=expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
        )

        # Add raw layer data for visualization (during eval only)
        # Threshold routing is eval-only, so always collect layer_data
        if not torch.is_grad_enabled():
            # Compute weights for visualization (apply router activation to logits)
            weights = self.apply_router_activation(router_logits_flat, self.config.router_activation)
            metrics['layer_data'] = {
                'weights': weights.reshape(-1).detach(),
                'fanout': counts.detach(),
                'cutoffs': self.cutoff_ema.clone().detach(),  # type: ignore
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics
