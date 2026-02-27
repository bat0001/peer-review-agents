"""ExpertEngine: core routed-expert compute without scatter."""

from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from ..router_utils import apply_router_activation
from .common import ExpertEngineCommon


class ExpertEngine(ExpertEngineCommon, nn.Module):
    """Expert computation engine returning pre-scatter routed outputs."""

    def __init__(self, config, n_routed_experts: int):
        super().__init__()
        self.config = config
        self.n_routed_experts = n_routed_experts

        self.router = nn.Linear(config.n_embd, n_routed_experts, bias=False)

        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(n_routed_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(n_routed_experts)
        ])

        self.register_buffer("cutoff_ema_raw", torch.zeros(n_routed_experts))
        self.register_buffer("cutoff_ema_updates", torch.zeros(1, dtype=torch.long))
        self.register_buffer("cutoff_accum_sum", torch.zeros(n_routed_experts), persistent=False)
        self.register_buffer("cutoff_accum_count", torch.zeros(1, dtype=torch.long), persistent=False)

        self._init_engine_weights()

    def forward(
        self,
        x: Tensor,
        layer_idx: int = 0,
        is_shared: bool = False,
        policy: str = "topk",
        routing_chunk_seqs: Optional[int] = None,
    ) -> Tuple[Tensor, Tensor, Tensor, Tensor, Optional[Tensor], Dict[str, Tensor]]:
        """Single engine forward where policy only changes routing selection."""
        if policy not in {"topk", "threshold"}:
            raise ValueError(f"policy must be 'topk' or 'threshold', got {policy}")

        bsz, seqlen, hidden = x.shape
        n_tokens = bsz * seqlen
        x_flat = x.view(-1, hidden)

        router_logits = self.router(x).float()
        router_logits_flat = router_logits.view(-1, self.n_routed_experts)
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity,
        )

        if policy == "topk":
            (
                indices_batched,
                weights_batched,
                valid_mask,
                cutoffs,
                k_actual,
                above_counts,
                capacity_config,
                cutoff_ema_for_metrics,
            ) = self._route_topk(
                x=x,
                router_logits=router_logits,
                router_logits_flat=router_logits_flat,
                all_weights=all_weights,
                n_tokens=n_tokens,
                is_shared=is_shared,
                routing_chunk_seqs=routing_chunk_seqs,
            )
            cutoffs_for_metrics = cutoffs
        else:
            (
                selection_result,
                cutoffs_for_metrics,
                capacity_config,
                cutoff_ema_for_metrics,
            ) = self._route_threshold(
                router_logits_flat=router_logits_flat,
                all_weights=all_weights,
                n_tokens=n_tokens,
                is_shared=is_shared,
            )

            if selection_result is None:
                h_flat = torch.zeros(0, hidden, device=x.device, dtype=x.dtype)
                indices_flat = torch.zeros(0, device=x.device, dtype=torch.long)
                weights_flat = torch.zeros(0, device=x.device, dtype=x.dtype)
                fanout = torch.zeros(n_tokens, device=x.device, dtype=torch.float32)

                metrics = self._compute_metrics(
                    router_logits_flat=router_logits_flat,
                    indices=indices_flat,
                    weights=weights_flat,
                    fanout=fanout,
                    cutoffs=cutoffs_for_metrics,
                    n_tokens=n_tokens,
                    layer_idx=layer_idx,
                    k_actual=torch.zeros(self.n_routed_experts, device=x.device),
                    above_counts=torch.zeros(self.n_routed_experts, device=x.device),
                    capacity_config=capacity_config,
                    cutoff_ema_for_metrics=cutoff_ema_for_metrics,
                )
                return h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics

            (
                indices_batched,
                weights_batched,
                valid_mask,
                k_actual,
                above_counts,
            ) = selection_result

        indices_flat = indices_batched[valid_mask]
        weights_flat = weights_batched[valid_mask]
        fanout = torch.bincount(indices_flat, minlength=n_tokens).to(torch.float32)

        h_batched_flat = self._compute_expert_outputs(x_flat=x_flat, indices_batched=indices_batched)
        h_flat = h_batched_flat[valid_mask.view(-1)]

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            indices=indices_flat,
            weights=weights_flat,
            fanout=fanout,
            cutoffs=cutoffs_for_metrics,
            n_tokens=n_tokens,
            layer_idx=layer_idx,
            k_actual=k_actual,
            above_counts=above_counts,
            capacity_config=capacity_config,
            cutoff_ema_for_metrics=cutoff_ema_for_metrics,
        )

        return h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics

    def _route_topk(
        self,
        x: Tensor,
        router_logits: Tensor,
        router_logits_flat: Tensor,
        all_weights: Tensor,
        n_tokens: int,
        is_shared: bool,
        routing_chunk_seqs: Optional[int],
    ):
        bsz, seqlen, _ = x.shape
        if routing_chunk_seqs is None:
            plan = self._build_routing_plan(
                policy="topk",
                router_logits_for_selection=router_logits_flat,
                n_tokens_for_k=n_tokens,
                is_shared=is_shared,
                topk_scale=1,
            )
            indices_batched = plan["topk_indices"]
            cutoffs = plan["cutoffs"]
            cutoff_ema_for_metrics = plan["cutoff_ema_for_metrics"]
        else:
            if routing_chunk_seqs <= 0:
                raise ValueError(f"routing_chunk_seqs must be positive, got {routing_chunk_seqs}")
            if routing_chunk_seqs > bsz:
                raise ValueError(f"routing_chunk_seqs {routing_chunk_seqs} cannot exceed batch size {bsz}")
            if bsz % routing_chunk_seqs != 0:
                raise ValueError(
                    f"Batch size {bsz} must be divisible by routing_chunk_seqs {routing_chunk_seqs}"
                )

            n_chunks = bsz // routing_chunk_seqs
            chunk_size = routing_chunk_seqs * seqlen
            router_logits_chunked = router_logits.view(n_chunks, chunk_size, self.n_routed_experts)

            k = self._compute_k_target(n_tokens=chunk_size, is_shared=is_shared)
            if k <= 0:
                raise ValueError(
                    f"k must be positive (got {k} from chunk_size={chunk_size}, "
                    f"G={self.config.granularity}, E={self.config.expansion})"
                )

            topk_values, topk_indices = torch.topk(
                router_logits_chunked.transpose(1, 2),
                k=min(k, chunk_size),
                dim=-1,
            )
            cutoffs = topk_values[:, :, -1]

            with torch.no_grad():
                avg_cutoffs = cutoffs.mean(dim=0)
                self._accumulate_cutoffs(avg_cutoffs)

            chunk_offsets = torch.arange(n_chunks, device=x.device).view(n_chunks, 1, 1) * chunk_size
            global_topk_indices = topk_indices + chunk_offsets
            indices_batched = global_topk_indices.permute(1, 0, 2).reshape(self.n_routed_experts, n_chunks * k)

        weights_batched = torch.gather(all_weights.t(), dim=1, index=indices_batched)
        valid_mask = torch.ones_like(indices_batched, dtype=torch.bool)

        return (
            indices_batched,
            weights_batched,
            valid_mask,
            cutoffs,
            None,
            None,
            None,
            cutoff_ema_for_metrics if routing_chunk_seqs is None else self._effective_cutoff(),
        )

    def _route_threshold(
        self,
        router_logits_flat: Tensor,
        all_weights: Tensor,
        n_tokens: int,
        is_shared: bool,
    ):
        plan = self._build_routing_plan(
            policy="threshold",
            router_logits_for_selection=router_logits_flat,
            n_tokens_for_k=n_tokens,
            is_shared=is_shared,
        )
        selection_result = self._threshold_selection_batched(
            above_mask=plan["above_mask"],
            all_weights=all_weights,
            k_actual=plan["k_actual"],
            topk_indices=plan["topk_indices"],
        )
        if selection_result is not None:
            selection_result = (
                selection_result[0],
                selection_result[1],
                selection_result[2],
                plan["k_actual"],
                plan["above_counts"],
            )
        return (
            selection_result,
            plan["cutoffs_for_metrics"],
            plan["capacity_config"],
            plan["cutoff_ema_for_metrics"],
        )

    def _batched_expert_forward(self, x_batched: Tensor) -> Tensor:
        """Batched expert MLP forward pass (no bias, ReLU^2)."""
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        h = torch.bmm(x_batched, weight1_3d.transpose(1, 2))
        h = F.relu(h).square()
        h = torch.bmm(h, weight2_3d.transpose(1, 2))
        return h

    def _compute_expert_outputs(self, x_flat: Tensor, indices_batched: Tensor) -> Tensor:
        """Gather tokens, run expert forward, and flatten to (E*k, C)."""
        x_batched = x_flat[indices_batched]
        h = self._batched_expert_forward(x_batched)
        return h.view(-1, h.shape[-1])
