"""ScatterMoE token-choice MLPs backed by ScatterMoE Triton kernels."""

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .model_base import BaseMLP, ModelConfig
from .router_utils import apply_router_activation
from scattermoe.scattermoe.parallel_experts import parallel_linear, flatten_sort_count


class ScatterMoETokenChoiceMLP(BaseMLP):
    """Token-choice MoE MLP using ScatterMoE kernels."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        assert config.n_experts is not None, "n_experts must be set for scattermoe_tc"
        assert config.expert_dim is not None, "expert_dim must be set for scattermoe_tc"
        if config.n_experts % config.expansion != 0:
            raise ValueError(
                "scattermoe_tc requires n_experts divisible by expansion "
                f"(got n_experts={config.n_experts}, expansion={config.expansion})"
            )

        self.top_k = min(config.n_experts // config.expansion, config.n_experts)
        self.load_balance_method = config.load_balance_method

        self.router = nn.Linear(config.n_embd, config.n_experts, bias=False)
        self.expert_weight1 = nn.Parameter(torch.empty(config.n_experts * config.expert_dim, config.n_embd))
        self.expert_weight2 = nn.Parameter(torch.empty(config.n_experts * config.n_embd, config.expert_dim))

        self.register_buffer("router_bias", torch.zeros(config.n_experts))
        self.register_buffer("bias_count_accum", torch.zeros(config.n_experts), persistent=False)
        self.register_buffer("bias_count_steps", torch.tensor(0, dtype=torch.long), persistent=False)

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        n_tokens = B * T
        n_experts = self.config.n_experts
        top_k = self.top_k

        x_flat = x.view(-1, C)

        router_logits = self.router(x).float()
        router_logits_flat = router_logits.view(-1, n_experts)

        all_weights, _shared = apply_router_activation(
            router_logits_flat,
            activation=self.config.router_activation,
            G=self.config.granularity,
        )
        if all_weights is None:
            raise ValueError("router_activation='softmax_k' is not supported for scattermoe_tc")

        selection_logits = router_logits_flat
        if self.load_balance_method == "deepseek":
            selection_logits = selection_logits + self.router_bias

        _, expert_idxs = torch.topk(selection_logits, k=top_k, dim=1)
        gates = torch.gather(all_weights, dim=1, index=expert_idxs)

        if self.load_balance_method == "deepseek" and self.training:
            with torch.no_grad():
                counts = torch.bincount(expert_idxs.flatten(), minlength=n_experts).to(self.bias_count_accum.dtype)
                self.bias_count_accum.add_(counts)
                self.bias_count_steps.add_(1)

        sorted_expert_idxs, sorted_scattered_idxs, expert_offsets = flatten_sort_count(
            expert_idxs, num_experts=n_experts
        )

        w1 = (
            self.expert_weight1.to(x.dtype)
            .view(n_experts, self.config.expert_dim, C)
            .permute(0, 2, 1)
            .contiguous()
        )
        h = parallel_linear(
            x_flat,
            w1,
            top_k,
            sorted_expert_idxs,
            sorted_scattered_idxs,
            expert_offsets,
            grouped_out=True,
        )
        h = F.relu(h).square()

        w2 = (
            self.expert_weight2.to(x.dtype)
            .view(n_experts, C, self.config.expert_dim)
            .permute(0, 2, 1)
            .contiguous()
        )
        y = parallel_linear(
            h.to(x.dtype),
            w2,
            1,
            sorted_expert_idxs,
            sorted_scattered_idxs,
            expert_offsets,
            gates=gates.to(x.dtype),
            grouped_in=True,
            grouped_out=False,
        )

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            expert_idxs=expert_idxs,
            gates=gates,
            n_tokens=n_tokens,
            layer_idx=layer_idx,
        )

        if self.load_balance_method == "aux" or self.load_balance_method == "aux_error":
            mask = torch.zeros_like(all_weights)
            mask.scatter_(1, expert_idxs, 1.0 / float(top_k))
            f = mask.mean(dim=0) * n_experts
            f = f if self.load_balance_method == "aux" else (f - 1.0)
            p = all_weights.mean(dim=0)
            metrics["aux_loss"] = torch.sum(f * p)

        y = y.view(B, T, C).to(x.dtype)
        return y, metrics

    def _compute_metrics(
        self,
        router_logits_flat: torch.Tensor,
        expert_idxs: torch.Tensor,
        gates: torch.Tensor,
        n_tokens: int,
        layer_idx: int,
    ) -> Dict[str, torch.Tensor]:
        expert_counts = torch.bincount(expert_idxs.flatten(), minlength=self.config.n_experts).float()
        expert_usage = expert_counts / n_tokens

        token_fanout = torch.full(
            (n_tokens,),
            float(expert_idxs.size(1)),
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

        repr_layers = {
            0,
            1,
            self.config.n_layer // 4,
            self.config.n_layer // 2,
            3 * self.config.n_layer // 4,
            self.config.n_layer - 1,
        }
        if layer_idx in repr_layers:
            metrics[f"repr_L{layer_idx}_expert_usage"] = expert_usage
            if self.load_balance_method == "deepseek":
                metrics[f"repr_L{layer_idx}_cutoff_ema"] = self.router_bias.clone()

        return metrics

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


class ScatterMoETokenChoiceSharedMLP(BaseMLP):
    """Token-choice MoE MLP with a shared expert using ScatterMoE kernels."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)

        assert config.n_experts is not None, "n_experts must be set for tc_shared"
        assert config.expert_dim is not None, "expert_dim must be set for tc_shared"
        if config.n_experts < 2:
            raise ValueError(f"tc_shared requires at least 1 routed expert (got n_experts={config.n_experts})")
        if config.router_activation == "softmax_e_shared_out":
            raise ValueError("router_activation='softmax_e_shared_out' is not supported for tc_shared")

        n_routed_experts = config.n_experts - 1
        if n_routed_experts % config.expansion != 0:
            raise ValueError(
                "tc_shared requires routed experts divisible by expansion "
                f"(got routed={n_routed_experts}, expansion={config.expansion})"
            )
        if config.granularity < 2:
            raise ValueError(f"tc_shared requires granularity >= 2 (got {config.granularity})")

        self.n_routed_experts = n_routed_experts
        self.top_k = min(config.granularity - 1, n_routed_experts)
        self.load_balance_method = config.load_balance_method

        self.router = nn.Linear(config.n_embd, n_routed_experts, bias=False)
        self.expert_weight1 = nn.Parameter(torch.empty(n_routed_experts * config.expert_dim, config.n_embd))
        self.expert_weight2 = nn.Parameter(torch.empty(n_routed_experts * config.n_embd, config.expert_dim))
        self.shared_weight1 = nn.Parameter(torch.empty(config.expert_dim, config.n_embd))
        self.shared_weight2 = nn.Parameter(torch.empty(config.n_embd, config.expert_dim))

        self.register_buffer("router_bias", torch.zeros(n_routed_experts))
        self.register_buffer("bias_count_accum", torch.zeros(n_routed_experts), persistent=False)
        self.register_buffer("bias_count_steps", torch.tensor(0, dtype=torch.long), persistent=False)

    def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        B, T, C = x.shape
        n_tokens = B * T
        n_routed_experts = self.n_routed_experts
        top_k = self.top_k

        x_flat = x.view(-1, C)

        router_logits = self.router(x).float()
        router_logits_flat = router_logits.view(-1, n_routed_experts)

        all_weights, _shared = apply_router_activation(
            router_logits_flat,
            activation=self.config.router_activation,
            G=self.config.granularity,
            include_shared=False,
        )
        if all_weights is None:
            raise ValueError("router_activation='softmax_k' is not supported for tc_shared")

        selection_logits = router_logits_flat
        if self.load_balance_method == "deepseek":
            selection_logits = selection_logits + self.router_bias

        _, expert_idxs = torch.topk(selection_logits, k=top_k, dim=1)
        gates = torch.gather(all_weights, dim=1, index=expert_idxs)

        if self.load_balance_method == "deepseek" and self.training:
            with torch.no_grad():
                counts = torch.bincount(expert_idxs.flatten(), minlength=n_routed_experts).to(self.bias_count_accum.dtype)
                self.bias_count_accum.add_(counts)
                self.bias_count_steps.add_(1)

        sorted_expert_idxs, sorted_scattered_idxs, expert_offsets = flatten_sort_count(
            expert_idxs, num_experts=n_routed_experts
        )

        w1 = (
            self.expert_weight1.to(x.dtype)
            .view(n_routed_experts, self.config.expert_dim, C)
            .permute(0, 2, 1)
            .contiguous()
        )
        h = parallel_linear(
            x_flat,
            w1,
            top_k,
            sorted_expert_idxs,
            sorted_scattered_idxs,
            expert_offsets,
            grouped_out=True,
        )
        h = F.relu(h).square()

        w2 = (
            self.expert_weight2.to(x.dtype)
            .view(n_routed_experts, C, self.config.expert_dim)
            .permute(0, 2, 1)
            .contiguous()
        )
        y_routed = parallel_linear(
            h.to(x.dtype),
            w2,
            1,
            sorted_expert_idxs,
            sorted_scattered_idxs,
            expert_offsets,
            gates=gates.to(x.dtype),
            grouped_in=True,
            grouped_out=False,
        )

        shared_h = F.linear(x_flat, self.shared_weight1)
        shared_h = F.relu(shared_h).square()
        shared_h = shared_h.to(x.dtype)
        shared_output = F.linear(shared_h, self.shared_weight2)

        y = y_routed + shared_output

        metrics = self._compute_metrics(
            router_logits_flat=router_logits_flat,
            expert_idxs=expert_idxs,
            gates=gates,
            n_tokens=n_tokens,
            layer_idx=layer_idx,
        )

        if self.load_balance_method == "aux" or self.load_balance_method == "aux_error":
            mask = torch.zeros_like(all_weights)
            mask.scatter_(1, expert_idxs, 1.0 / float(top_k))
            f = mask.mean(dim=0) * n_routed_experts  # Scale so uniform target is 1.
            f = f if self.load_balance_method == "aux" else (f - 1.0)
            p = all_weights.mean(dim=0)
            metrics["aux_loss"] = torch.sum(f * p)

        y = y.view(B, T, C).to(x.dtype)
        return y, metrics

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
        expert_usage = torch.cat([
            torch.ones(1, device=routed_usage.device, dtype=routed_usage.dtype),
            routed_usage,
        ])

        token_fanout = torch.full(
            (n_tokens,),
            float(expert_idxs.size(1) + 1),
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

        repr_layers = {
            0,
            1,
            self.config.n_layer // 4,
            self.config.n_layer // 2,
            3 * self.config.n_layer // 4,
            self.config.n_layer - 1,
        }
        if layer_idx in repr_layers:
            metrics[f"repr_L{layer_idx}_expert_usage"] = expert_usage
            metrics[f"repr_L{layer_idx}_E0_expert_usage"] = routed_usage[0]
            metrics[f"repr_L{layer_idx}_Elast_expert_usage"] = routed_usage[-1]
            if self.load_balance_method == "deepseek":
                metrics[f"repr_L{layer_idx}_cutoff_ema"] = self.router_bias.clone()
                metrics[f"repr_L{layer_idx}_E0_cutoff_ema"] = self.router_bias[0].clone()
                metrics[f"repr_L{layer_idx}_Elast_cutoff_ema"] = self.router_bias[-1].clone()

        return metrics

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
