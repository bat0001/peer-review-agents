"""ScatterMoE token-choice MLP (`token_choice`).

Provenance:
- Core token-choice expert kernels/operators are used from ScatterMoE:
  https://github.com/shawntan/scattermoe
- This module adapts those ops to this repository's model/config/metrics API.
"""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.utils.repr_layers import get_repr_layers
from .model_base import BaseMLP, ModelConfig
from .router_utils import apply_router_activation
# Imported from vendored ScatterMoE source tree in this repo (`scattermoe/`).
from scattermoe.scattermoe.parallel_experts import flatten_sort_count, parallel_linear


class TokenChoiceMLP(BaseMLP):
    """Token-choice MoE MLP using ScatterMoE kernels."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        assert config.n_experts is not None, "n_experts must be set for token_choice"
        assert config.expert_dim is not None, "expert_dim must be set for token_choice"

        self.shared_expert = bool(getattr(config, "shared_expert", False))
        self.n_routed_experts = config.n_experts - 1 if self.shared_expert else config.n_experts

        if self.n_routed_experts < 1:
            raise ValueError(
                "token_choice requires at least 1 routed expert "
                f"(got n_experts={config.n_experts}, shared_expert={self.shared_expert})"
            )
        if self.n_routed_experts % config.expansion != 0:
            raise ValueError(
                "token_choice requires routed experts divisible by expansion "
                f"(got routed={self.n_routed_experts}, expansion={config.expansion})"
            )
        if self.shared_expert and config.granularity < 2:
            raise ValueError(f"token_choice with shared_expert=true requires granularity >= 2 (got {config.granularity})")

        if self.shared_expert:
            self.top_k = min(config.granularity - 1, self.n_routed_experts)
        else:
            self.top_k = min(self.n_routed_experts // config.expansion, self.n_routed_experts)
        if self.top_k < 1:
            raise ValueError(
                f"token_choice requires top_k >= 1 (got top_k={self.top_k}, "
                f"n_routed_experts={self.n_routed_experts})"
            )

        self.load_balance_method = config.load_balance_method

        self.router = nn.Linear(config.n_embd, self.n_routed_experts, bias=False)
        self.expert_weight1 = nn.Parameter(torch.empty(self.n_routed_experts * config.expert_dim, config.n_embd))
        self.expert_weight2 = nn.Parameter(torch.empty(self.n_routed_experts * config.n_embd, config.expert_dim))

        if self.shared_expert:
            self.shared_weight1 = nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
            self.shared_weight2 = nn.Parameter(torch.empty(config.n_embd, config.expert_dim))

        self.register_buffer("router_bias", torch.zeros(self.n_routed_experts))
        self.register_buffer("bias_count_accum", torch.zeros(self.n_routed_experts), persistent=False)
        self.register_buffer("bias_count_steps", torch.tensor(0, dtype=torch.long), persistent=False)

    def _route(
        self,
        router_logits_flat: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        all_weights, _shared = apply_router_activation(
            router_logits_flat,
            activation=self.config.router_activation,
            G=self.config.granularity,
            include_shared=(not self.shared_expert),
        )
        if all_weights is None:
            raise ValueError("router_activation='softmax_k' is not supported for token_choice")

        selection_logits = router_logits_flat
        if self.load_balance_method == "deepseek":
            selection_logits = selection_logits + self.router_bias

        _, expert_idxs = torch.topk(selection_logits, k=self.top_k, dim=1)
        gates = torch.gather(all_weights, dim=1, index=expert_idxs)
        return all_weights, expert_idxs, gates

    def _accumulate_bias_counts(self, expert_idxs: torch.Tensor) -> None:
        if self.load_balance_method != "deepseek" or not self.training:
            return
        with torch.no_grad():
            counts = torch.bincount(expert_idxs.flatten(), minlength=self.n_routed_experts).to(self.bias_count_accum.dtype)
            self.bias_count_accum.add_(counts)
            self.bias_count_steps.add_(1)

    def _compute_routed_output(
        self,
        x_flat: torch.Tensor,
        width: int,
        expert_idxs: torch.Tensor,
        gates: torch.Tensor,
    ) -> torch.Tensor:
        sorted_expert_idxs, sorted_scattered_idxs, expert_offsets = flatten_sort_count(
            expert_idxs,
            num_experts=self.n_routed_experts,
        )

        w1 = (
            self.expert_weight1.to(x_flat.dtype)
            .view(self.n_routed_experts, self.config.expert_dim, width)
            .permute(0, 2, 1)
            .contiguous()
        )
        h = parallel_linear(
            x_flat,
            w1,
            self.top_k,
            sorted_expert_idxs,
            sorted_scattered_idxs,
            expert_offsets,
            grouped_out=True,
        )
        h = F.relu(h).square()

        w2 = (
            self.expert_weight2.to(x_flat.dtype)
            .view(self.n_routed_experts, width, self.config.expert_dim)
            .permute(0, 2, 1)
            .contiguous()
        )
        return parallel_linear(
            h.to(x_flat.dtype),
            w2,
            1,
            sorted_expert_idxs,
            sorted_scattered_idxs,
            expert_offsets,
            gates=gates.to(x_flat.dtype),
            grouped_in=True,
            grouped_out=False,
        )

    def _compute_shared_output(self, x_flat: torch.Tensor, target_dtype: torch.dtype) -> torch.Tensor:
        shared_h = F.linear(x_flat, self.shared_weight1)
        shared_h = F.relu(shared_h).square()
        shared_h = shared_h.to(target_dtype)
        return F.linear(shared_h, self.shared_weight2)

    def _compute_metrics(
        self,
        router_logits_flat: torch.Tensor,
        expert_idxs: torch.Tensor,
        gates: torch.Tensor,
        n_tokens: int,
        layer_idx: int,
    ) -> Dict[str, torch.Tensor]:
        expert_counts = torch.bincount(expert_idxs.flatten(), minlength=self.n_routed_experts).float()
        routed_usage = expert_counts / n_tokens
        if self.shared_expert:
            expert_usage = torch.cat([
                torch.ones(1, device=routed_usage.device, dtype=routed_usage.dtype),
                routed_usage,
            ])
            fanout = float(expert_idxs.size(1) + 1)
        else:
            expert_usage = routed_usage
            fanout = float(expert_idxs.size(1))

        token_fanout = torch.full(
            (n_tokens,),
            fanout,
            device=router_logits_flat.device,
            dtype=router_logits_flat.dtype,
        )

        metrics = {
            "expert_usage": expert_usage,
            "avg_experts_per_token": token_fanout.mean(),
            "max_experts_per_token": token_fanout.max(),
            "tokens_with_no_expert": (token_fanout == 0).float().mean(),
            "tokens_with_1_expert": (token_fanout == 1).float().mean(),
            "tokens_with_2+_experts": (token_fanout >= 2).float().mean(),
            "activation_weight_mean": gates.mean(),
            "activation_weight_std": gates.std(),
            "activation_weight_max": gates.max(),
            "activation_weight_min": gates.min(),
            "router_logit_mean": router_logits_flat.mean(),
            "router_logit_std": router_logits_flat.std(),
        }

        repr_layers = get_repr_layers(self.config.n_layer)
        if layer_idx in repr_layers:
            metrics[f"repr_L{layer_idx}_expert_usage"] = expert_usage
            if self.shared_expert:
                metrics[f"repr_L{layer_idx}_E0_expert_usage"] = routed_usage[0]
                metrics[f"repr_L{layer_idx}_Elast_expert_usage"] = routed_usage[-1]
            if self.load_balance_method == "deepseek":
                metrics[f"repr_L{layer_idx}_cutoff_ema"] = self.router_bias.clone()
                if self.shared_expert:
                    metrics[f"repr_L{layer_idx}_E0_cutoff_ema"] = self.router_bias[0].clone()
                    metrics[f"repr_L{layer_idx}_Elast_cutoff_ema"] = self.router_bias[-1].clone()

        return metrics

    def _add_aux_loss(self, metrics: Dict[str, torch.Tensor], all_weights: torch.Tensor, expert_idxs: torch.Tensor) -> None:
        if self.load_balance_method not in {"aux", "aux_error"}:
            return
        mask = torch.zeros_like(all_weights)
        mask.scatter_(1, expert_idxs, 1.0 / float(self.top_k))
        f = mask.mean(dim=0) * self.n_routed_experts
        if self.load_balance_method == "aux_error":
            f = f - 1.0
        metrics["aux_loss"] = torch.sum(f * all_weights.mean(dim=0))

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        n_tokens = B * T
        x_flat = x.view(-1, C)

        router_logits_flat = self.router(x).float().view(-1, self.n_routed_experts)
        all_weights, expert_idxs, gates = self._route(router_logits_flat)

        self._accumulate_bias_counts(expert_idxs)
        y = self._compute_routed_output(x_flat, C, expert_idxs, gates)

        if self.shared_expert:
            y = y + self._compute_shared_output(x_flat, x.dtype)

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            expert_idxs=expert_idxs,
            gates=gates,
            n_tokens=n_tokens,
            layer_idx=layer_idx,
        )
        self._add_aux_loss(metrics, all_weights, expert_idxs)

        return y.view(B, T, C).to(x.dtype), metrics

    def finalize_bias_update(self) -> None:
        if self.load_balance_method != "deepseek":
            return
        if self.bias_count_steps.item() == 0:
            return

        counts = self.bias_count_accum
        if torch.distributed.is_initialized():
            torch.distributed.all_reduce(counts, op=torch.distributed.ReduceOp.SUM)

        counts = counts / float(self.bias_count_steps.item())
        target = counts.mean()
        delta = self.config.deepseek_bias_lr * torch.sign(target - counts)
        with torch.no_grad():
            self.router_bias.add_(delta)
            self.bias_count_accum.zero_()
            self.bias_count_steps.zero_()
