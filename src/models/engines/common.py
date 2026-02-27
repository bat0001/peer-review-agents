"""Shared engine utilities for expert-choice backends."""

from typing import Dict, List, Optional

import torch
import torch.nn as nn
from torch import Tensor


class ExpertEngineCommon:
    """Common cutoff/metrics/init logic used by DP and EP engines."""

    def _compute_k_target(self, n_tokens: int, is_shared: bool) -> int:
        """Compute per-expert target token count for routing selection."""
        if is_shared:
            g = self.config.granularity
            e = self.config.expansion
            k_target = int(n_tokens * (g - 1) // (g * e))
        else:
            k_target = int(n_tokens // self.config.expansion)
        return min(k_target, n_tokens)

    def _accumulate_cutoffs(self, cutoffs: Tensor):
        """Accumulate cutoffs for delayed EMA update at step boundary."""
        if self.training:
            self.cutoff_accum_sum.add_(cutoffs.detach())
            self.cutoff_accum_count.add_(1)

    def _build_routing_plan(
        self,
        policy: str,
        router_logits_for_selection: Tensor,
        n_tokens_for_k: int,
        is_shared: bool,
        topk_scale: int = 1,
    ) -> Dict[str, Optional[Tensor]]:
        """Build a shared non-chunked routing plan for DP/EP backends."""
        if policy not in {"topk", "threshold"}:
            raise ValueError(f"policy must be 'topk' or 'threshold', got {policy}")

        total_tokens = router_logits_for_selection.shape[0]

        if policy == "topk":
            k_target = self._compute_k_target(n_tokens=n_tokens_for_k, is_shared=is_shared)
            k_select = min(k_target * topk_scale, total_tokens)
            topk_values, topk_indices = torch.topk(
                router_logits_for_selection.t(),
                k=k_select,
                dim=1,
                sorted=True,
            )
            cutoffs = topk_values[:, -1]
            self._accumulate_cutoffs(cutoffs)
            return {
                "topk_indices": topk_indices,
                "topk_values": topk_values,
                "cutoffs": cutoffs,
                "cutoffs_for_metrics": cutoffs,
                "k_actual": None,
                "above_counts": None,
                "above_mask": None,
                "capacity_config": None,
                "cutoff_ema_for_metrics": self._effective_cutoff(),
            }

        effective_cutoff = self._effective_cutoff()
        above_mask = router_logits_for_selection >= effective_cutoff.unsqueeze(0)
        above_counts = above_mask.sum(dim=0)
        capacity_config = None
        topk_indices = None
        topk_values = None

        if self.training:
            k_target = self._compute_k_target(n_tokens=n_tokens_for_k, is_shared=is_shared)
            if self.config.expert_capacity_factor >= 0:
                k_min = int(k_target * (1 - self.config.expert_capacity_factor))
                k_max = int(k_target * (1 + self.config.expert_capacity_factor))
                capacity_config = {"k_min": k_min, "k_max": k_max}
                with torch.no_grad():
                    topk_values, topk_indices = torch.topk(
                        router_logits_for_selection.t(),
                        k=min(k_max, total_tokens),
                        dim=1,
                        sorted=True,
                    )
                    k_idx = min(k_target - 1, topk_values.shape[1] - 1)
                    cutoffs = topk_values[:, k_idx]
            else:
                with torch.no_grad():
                    topk_values, _ = torch.topk(
                        router_logits_for_selection.t(),
                        k=min(k_target, total_tokens),
                        dim=1,
                        sorted=True,
                    )
                    cutoffs = topk_values[:, -1]
            self._accumulate_cutoffs(cutoffs)
        else:
            cutoffs = effective_cutoff

        if capacity_config is not None:
            k_actual = torch.clamp(above_counts, capacity_config["k_min"], capacity_config["k_max"])
        else:
            k_actual = above_counts

        if self.training and self.cutoff_accum_count.item() > 0:
            cutoffs_for_metrics = self.cutoff_accum_sum / self.cutoff_accum_count
        else:
            cutoffs_for_metrics = effective_cutoff

        return {
            "topk_indices": topk_indices,
            "topk_values": topk_values,
            "cutoffs": cutoffs,
            "cutoffs_for_metrics": cutoffs_for_metrics,
            "k_actual": k_actual,
            "above_counts": above_counts,
            "above_mask": above_mask,
            "capacity_config": capacity_config,
            "cutoff_ema_for_metrics": effective_cutoff,
        }

    def _threshold_indices_list(
        self,
        above_mask: Tensor,
        k_actual: Tensor,
        topk_indices: Optional[Tensor] = None,
    ) -> List[Tensor]:
        """Materialize variable-length selected indices for threshold routing."""
        indices_list: List[Tensor] = []
        k_actual_cpu = k_actual.cpu()
        for expert_idx in range(k_actual.shape[0]):
            k = int(k_actual_cpu[expert_idx])
            if k == 0:
                indices_list.append(torch.zeros(0, device=above_mask.device, dtype=torch.long))
                continue
            if topk_indices is not None:
                indices_list.append(topk_indices[expert_idx, :k])
            else:
                indices_list.append(torch.nonzero(above_mask[:, expert_idx], as_tuple=True)[0])
        return indices_list

    def _threshold_selection_batched(
        self,
        above_mask: Tensor,
        all_weights: Tensor,
        k_actual: Tensor,
        topk_indices: Optional[Tensor] = None,
    ):
        """Materialize padded batched threshold selections for DP compute."""
        n_routed_experts = k_actual.shape[0]
        actual_k_max = int(k_actual.max().item())
        if actual_k_max == 0:
            return None

        indices_batched = torch.zeros(
            n_routed_experts,
            actual_k_max,
            device=above_mask.device,
            dtype=torch.long,
        )
        weights_batched = torch.zeros(
            n_routed_experts,
            actual_k_max,
            device=above_mask.device,
            dtype=all_weights.dtype,
        )
        valid_mask = torch.zeros(
            n_routed_experts,
            actual_k_max,
            device=above_mask.device,
            dtype=torch.bool,
        )

        indices_list = self._threshold_indices_list(
            above_mask=above_mask,
            k_actual=k_actual,
            topk_indices=topk_indices,
        )
        for expert_idx, active_indices in enumerate(indices_list):
            k = active_indices.numel()
            if k == 0:
                continue
            indices_batched[expert_idx, :k] = active_indices
            weights_batched[expert_idx, :k] = all_weights[active_indices, expert_idx]
            valid_mask[expert_idx, :k] = True

        return indices_batched, weights_batched, valid_mask

    @property
    def cutoff_ema(self) -> Tensor:
        """Effective (bias-corrected) cutoff used by threshold routing."""
        return self._effective_cutoff()

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
        cutoff_ema_for_metrics: Optional[Tensor] = None,
    ) -> Dict[str, Tensor]:
        """Compute routing metrics shared across backends."""
        token_fanout = fanout

        if k_actual is not None:
            expert_token_counts = k_actual.float()
        else:
            k_per_expert = len(indices) // self.n_routed_experts if self.n_routed_experts > 0 else 0
            expert_token_counts = torch.full(
                (self.n_routed_experts,),
                k_per_expert,
                dtype=torch.float32,
                device=indices.device,
            )

        expert_usage = expert_token_counts / n_tokens

        # Import here to avoid circular dependency.
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
            normalizer=fanout,
            indices=indices,
            above_counts=above_counts if capacity_config else None,
            k_min=capacity_config["k_min"] if capacity_config else None,
            k_max=capacity_config["k_max"] if capacity_config else None,
            n_tokens=n_tokens,
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
        """Finalize cutoff accumulation at training step boundary."""
        if self.cutoff_accum_count.item() > 0:
            if apply_update:
                cutoff_mean = self.cutoff_accum_sum / self.cutoff_accum_count
                alpha = self.config.cutoff_ema_alpha
                self.cutoff_ema_raw.mul_(alpha).add_(cutoff_mean, alpha=1 - alpha)
                self.cutoff_ema_updates.add_(1)
            self.cutoff_accum_sum.zero_()
            self.cutoff_accum_count.zero_()

    def sync_cutoff_state(self) -> Tensor:
        """Return raw cutoff EMA buffer for syncing across workers."""
        return self.cutoff_ema_raw

    def _init_engine_weights(self):
        """Initialize router and expert weights."""
        nn.init.xavier_uniform_(self.router.weight)
        for w in self.expert_weight1:
            nn.init.xavier_uniform_(w)
        for w in self.expert_weight2:
            nn.init.xavier_uniform_(w)
