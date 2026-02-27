"""Manual expert-parallel engine with a single policy-agnostic forward path."""

from typing import Dict, List, Optional, Tuple

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from ..router_utils import apply_router_activation
from ...ops.prealloc_all_to_all import prealloc_all_to_all
from .common import ExpertEngineCommon


class ParallelExperts(ExpertEngineCommon, nn.Module):
    def __init__(self, config, n_routed_experts: int):
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

        self.router = nn.Linear(config.n_embd, n_routed_experts, bias=False)

        self.expert_weight1 = nn.ParameterList([
            nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            for _ in range(self.local_experts)
        ])
        self.expert_weight2 = nn.ParameterList([
            nn.Parameter(torch.empty(config.n_embd, config.expert_dim))
            for _ in range(self.local_experts)
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
        """Single EP forward where policy only changes routing selection."""
        if policy not in {"topk", "threshold"}:
            raise ValueError(f"policy must be 'topk' or 'threshold', got {policy}")
        if routing_chunk_seqs is not None:
            raise ValueError("expert_parallel with routing_chunk_seqs is not supported in this release")

        bsz, seqlen, hidden = x.shape
        n_tokens = bsz * seqlen
        global_tokens = n_tokens * self.world_size

        x_flat = x.view(-1, hidden)

        router_logits = self.router(x).float()
        router_logits_flat = router_logits.view(-1, self.n_routed_experts)

        all_weights, shared_weights = apply_router_activation(
            router_logits_flat,
            self.config.router_activation,
            self.config.granularity,
        )

        with torch.no_grad():
            global_router_logits = torch.empty(
                (global_tokens, self.n_routed_experts),
                device=router_logits_flat.device,
                dtype=router_logits_flat.dtype,
            )
            dist.all_gather_into_tensor(global_router_logits, router_logits_flat)

        (
            indices_list,
            cutoffs,
            k_actual,
            above_counts,
            capacity_config,
            cutoff_ema_for_metrics,
        ) = self._select_global_routing(
            global_router_logits=global_router_logits,
            n_tokens=n_tokens,
            global_tokens=global_tokens,
            is_shared=is_shared,
            policy=policy,
        )

        expert_outputs_received, local_indices, expert_ids = self._dispatch_and_compute(
            indices_list=indices_list,
            x_flat=x_flat,
            n_tokens=n_tokens,
            hidden_size=hidden,
            device=x.device,
            dtype=x.dtype,
        )

        weights_flat = all_weights[local_indices, expert_ids]
        fanout = torch.bincount(local_indices, minlength=n_tokens).to(torch.float32)

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
            cutoff_ema_for_metrics=cutoff_ema_for_metrics,
        )

        return expert_outputs_received, local_indices, weights_flat, fanout, shared_weights, metrics

    def _select_global_routing(
        self,
        global_router_logits: Tensor,
        n_tokens: int,
        global_tokens: int,
        is_shared: bool,
        policy: str,
    ):
        plan = self._build_routing_plan(
            policy=policy,
            router_logits_for_selection=global_router_logits,
            n_tokens_for_k=global_tokens,
            is_shared=is_shared,
        )
        if policy == "topk":
            indices_list = [plan["topk_indices"][i] for i in range(self.n_routed_experts)]
            k_actual = None
            above_counts = None
        else:
            k_actual = plan["k_actual"]
            above_counts = plan["above_counts"]
            indices_list = self._threshold_indices_list(
                above_mask=plan["above_mask"],
                k_actual=k_actual,
                topk_indices=plan["topk_indices"],
            )
        return (
            indices_list,
            plan["cutoffs"],
            k_actual,
            above_counts,
            plan["capacity_config"],
            plan["cutoff_ema_for_metrics"],
        )

    def _dispatch_and_compute(
        self,
        indices_list: List[Tensor],
        x_flat: Tensor,
        n_tokens: int,
        hidden_size: int,
        device: torch.device,
        dtype: torch.dtype,
    ) -> Tuple[Tensor, Tensor, Tensor]:
        input_splits_sizes = []
        output_splits_sizes = []
        all_send_indices = []
        x_list = []
        k_actual_local = []

        expert_starts = self.local_experts * self.rank

        for i in range(self.local_experts):
            remote_expert_indices = indices_list[i::self.local_experts]
            local_mask = [
                (remote_expert_indices[r] >= self.rank * n_tokens)
                & (remote_expert_indices[r] < (self.rank + 1) * n_tokens)
                for r in range(self.world_size)
            ]
            send_indices = torch.cat(
                [remote_expert_indices[r][local_mask[r]] for r in range(self.world_size)],
                dim=0,
            )

            all_send_indices.append(send_indices % n_tokens)

            my_expert_indices = indices_list[i + expert_starts]
            output_splits_sizes.append([
                ((my_expert_indices >= r * n_tokens) & (my_expert_indices < (r + 1) * n_tokens)).sum().item()
                for r in range(self.world_size)
            ])
            input_splits_sizes.append([
                local_mask[r].sum().item()
                for r in range(self.world_size)
            ])

            k_actual_local.append(sum(output_splits_sizes[i]))
            x_list.append(x_flat[send_indices % n_tokens].contiguous())

        k_actual_max = max(k_actual_local) if k_actual_local else 0
        recv_offsets = [i * k_actual_max for i in range(self.local_experts)]

        tokens_received_flat = prealloc_all_to_all(
            x_list,
            output_splits_sizes,
            input_splits_sizes,
            hidden_size=hidden_size,
            device=device,
            dtype=dtype,
            recv_offsets=recv_offsets,
        )

        if k_actual_max > 0:
            tokens_received = tokens_received_flat.view(self.local_experts, k_actual_max, hidden_size)
        else:
            tokens_received = tokens_received_flat.view(self.local_experts, 0, hidden_size)

        h = self._batched_expert_forward(tokens_received)

        h_list = [h[i, :k_actual_local[i]] for i in range(self.local_experts)]
        expert_outputs_received = prealloc_all_to_all(
            h_list,
            input_splits_sizes,
            output_splits_sizes,
            hidden_size=hidden_size,
            device=h.device,
            dtype=h.dtype,
            recv_offsets=None,
        )

        local_indices = torch.cat(all_send_indices, dim=0)

        counts = [
            input_splits_sizes[i][r]
            for i in range(self.local_experts)
            for r in range(self.world_size)
        ]
        expert_ids_pattern = [
            r * self.local_experts + i
            for i in range(self.local_experts)
            for r in range(self.world_size)
        ]
        counts_tensor = torch.tensor(counts, device=device)
        expert_ids = torch.tensor(expert_ids_pattern, device=device).repeat_interleave(counts_tensor)

        return expert_outputs_received, local_indices, expert_ids

    def _batched_expert_forward(self, x_batched: Tensor) -> Tensor:
        """Batched expert MLP forward pass (no bias, ReLU^2)."""
        weight1_3d = torch.stack([w for w in self.expert_weight1])
        weight2_3d = torch.stack([w for w in self.expert_weight2])

        h = torch.bmm(x_batched, weight1_3d.transpose(1, 2))
        h = F.relu(h).square()
        h = torch.bmm(h, weight2_3d.transpose(1, 2))
        return h
