"""Expert Choice (EC) with Shared Expert - adds chunked routing to GEC_shared."""

from typing import Dict, Tuple

import torch
import torch.nn.functional as F

from .gec_shared import GECSharedMLP
from .router_utils import apply_router_activation, compute_fanout
from ..utils import compute_routing_metrics


class ECSharedMLP(GECSharedMLP):
    """EC with Shared Expert: Adds chunked routing to GECSharedMLP.

    Only overrides forward_topk() to implement chunked routing.
    Everything else (shared expert, threshold routing, etc.) inherited from GECSharedMLP.

    Routing granularity controlled by config.routing_chunk_seqs:
    - None: Global routing (falls back to GECSharedMLP behavior)
    - 1: Per-sequence routing
    - N: Per N-sequence routing
    """

    def __init__(self, config):
        super().__init__(config)
        # Routing chunk configuration
        self.routing_chunk_seqs = getattr(config, 'routing_chunk_seqs', None)

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Dispatch to top-k (chunked) or threshold routing.

        Training uses top-k; eval always uses threshold (handled by parent).
        """
        if (not self.training) or (self.routing_mode == 'threshold'):
            return super().forward(x, layer_idx)
        return self.forward_topk(x, layer_idx)

    def forward_topk(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """Forward pass with chunked top-k routing (if routing_chunk_seqs is set)."""

        # If no chunking, fall back to parent's global routing
        if self.routing_chunk_seqs is None:
            return super().forward(x, layer_idx)

        B, T, C = x.shape
        n_routed_experts = self.engine.n_routed_experts

        # Validate routing chunk configuration
        assert self.routing_chunk_seqs > 0, f"routing_chunk_seqs must be positive, got {self.routing_chunk_seqs}"
        assert B % self.routing_chunk_seqs == 0, f"Batch size {B} must be divisible by routing_chunk_seqs {self.routing_chunk_seqs}"
        assert self.routing_chunk_seqs <= B, f"routing_chunk_seqs {self.routing_chunk_seqs} cannot exceed batch size {B}"

        # Process shared expert (all tokens)
        x_flat = x.view(-1, C)
        shared_output = self._shared_expert_forward(x_flat)

        # Compute routing scores
        router_logits = self.engine.router(x).float()
        n_tokens = B * T

        # Chunking setup
        chunk_seqs = self.routing_chunk_seqs
        n_chunks = B // chunk_seqs
        chunk_size = chunk_seqs * T

        # Reshape for chunked processing
        router_logits_chunked = router_logits.view(n_chunks, chunk_size, n_routed_experts)

        # Compute k per chunk (GEC_shared formula)
        G = self.config.granularity
        E = self.config.expansion
        k = int(chunk_size * (G - 1) // (G * E))
        assert k > 0, f"k must be positive (got {k} from chunk_size={chunk_size}, G={G}, E={E})"

        # Select top-k per chunk
        router_logits_for_topk = router_logits_chunked.transpose(1, 2)  # (n_chunks, n_routed_experts, chunk_size)
        topk_values, topk_indices = torch.topk(router_logits_for_topk, k=min(k, chunk_size), dim=-1)

        # Get cutoffs and update EMA (average across chunks)
        cutoffs = topk_values[:, :, -1]  # (n_chunks, n_routed_experts)
        if self.training:
            with torch.no_grad():
                avg_cutoffs = cutoffs.mean(dim=0)
                # Accumulate cutoffs for EMA update at step boundary (same as engine)
                self.engine.cutoff_accum_sum.add_(avg_cutoffs.detach())
                self.engine.cutoff_accum_count.add_(1)

        # Adjust indices to global positions and group by expert
        chunk_offsets = torch.arange(n_chunks, device=x.device).view(n_chunks, 1, 1) * chunk_size
        global_topk_indices = topk_indices + chunk_offsets
        indices_flat = global_topk_indices.permute(1, 0, 2).reshape(n_routed_experts, n_chunks * k)
        permutation_indices = indices_flat.reshape(-1)

        # Router weights (apply activation to ALL logits, then gather)
        router_logits_flat = router_logits_chunked.reshape(n_tokens, n_routed_experts)
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity
        )
        weights_flat = torch.gather(all_weights.t(), dim=1, index=indices_flat)

        # Process routed experts (same as parent, but with chunked indices)
        x_permuted = x_flat[permutation_indices].view(n_routed_experts, n_chunks * k, C)

        # Stack 2D parameters to 3D before batched computation
        weight1_3d = torch.stack([w for w in self.engine.expert_weight1])
        weight2_3d = torch.stack([w for w in self.engine.expert_weight2])

        h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))
        h = F.relu(h).square()
        h = torch.bmm(h, weight2_3d.transpose(1, 2))

        # Compute fanout (routed experts only)
        fanout = compute_fanout(n_tokens, permutation_indices, x.device, torch.float32)

        # Fixed weighting rule: use raw routed weights.
        normalized_weights_flat = weights_flat.reshape(-1)
        if shared_weights is None:
            shared_weights = torch.ones_like(fanout)

        # Flatten outputs and scatter with fused weights
        h_flat = h.reshape(-1, C)
        output = self.scatter(
            h_flat,
            permutation_indices,
            n_tokens,
            normalized_weights_flat,
            shared_flat=shared_output,
            shared_weights=shared_weights,
        )
        output = output.view(B, T, C).to(x.dtype)

        # Metrics (same as parent)
        token_fanout = fanout

        expert_ids = torch.arange(n_routed_experts, device=x.device).view(-1, 1).expand_as(indices_flat)
        expert_token_counts = torch.zeros(n_routed_experts, device=x.device)
        expert_token_counts.scatter_add_(0, expert_ids.reshape(-1), torch.ones_like(expert_ids, dtype=torch.float32).reshape(-1))

        total_expert_usage = torch.cat([torch.ones(1, device=x.device), expert_token_counts / n_tokens])
        token_fanout_with_shared = token_fanout + 1.0

        metrics = compute_routing_metrics(
            cutoffs=cutoffs,
            cutoff_ema=self.engine.cutoff_ema.clone(),
            weights=weights_flat.reshape(-1),
            router_logits_flat=router_logits_flat,
            token_fanout=token_fanout_with_shared,
            expert_usage=total_expert_usage,
            layer_idx=layer_idx,
            n_layer=self.config.n_layer,
            model_instance=self,
            router_activation=self.config.router_activation,
            normalizer=fanout,  # Pass raw fanout for metrics
            indices=permutation_indices,
        )

        if not torch.is_grad_enabled():
            metrics['layer_data'] = {
                'weights': weights_flat.reshape(-1).detach(),
                'fanout': token_fanout_with_shared.detach(),
                'cutoffs': cutoffs.mean(dim=0).detach() if cutoffs.ndim == 2 else cutoffs.detach(),
                'router_logits': router_logits_flat.detach(),
            }

        return output, metrics
