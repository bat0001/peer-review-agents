"""Interactive inspector for GEC MLP forward breakdown.

Times major stages of the PyTorch GEC forward pass with CUDA events so we can
see where latency comes from (router, top-k, gather, expert MLP, scatter, etc.).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import nullcontext
from typing import Callable, Dict

import torch

from benchmark.mlp.core import add_routing_args, add_standard_args, args_to_config, setup_environment
from src.models.gec import GECMLP, GECMLPReference, GECTritonMLP, GECTritonMLP1 as GECTriton1MLP
from src.models.model_base import ModelConfig
from src.ops import gather as triton_gather
from src.ops import scatter as triton_scatter


class SectionTimer:
    """Utility that records per-section CUDA elapsed time in milliseconds."""

    def __init__(self) -> None:
        self._samples: Dict[str, list[float]] = defaultdict(list)

    def run(self, name: str, fn: Callable[[], torch.Tensor | tuple | None]) -> torch.Tensor | tuple | None:
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)

        torch.cuda.synchronize()
        start.record()
        result = fn()
        end.record()
        torch.cuda.synchronize()

        elapsed = start.elapsed_time(end)
        self._samples[name].append(float(elapsed))
        return result

    def summary(self) -> Dict[str, float]:
        return {name: sum(values) / len(values) for name, values in self._samples.items()}


def inspect_once(
    model: GECMLP | GECMLPReference | GECTritonMLP | GECTriton1MLP,
    token_tensor: torch.Tensor,
    density: float,
) -> Dict[str, float]:
    """Run a single forward breakdown with instrumentation."""
    timer = SectionTimer()

    B, T, C = token_tensor.shape
    n_tokens = B * T
    n_experts = model.router_w.shape[1]
    capacity = max(1, min(n_tokens, int(n_tokens * density)))

    # Mirrors src/models/gec.py forward with manual instrumentation.
    x_flat = token_tensor.view(-1, C)

    router_logits = timer.run(
        'router_einsum',
        lambda: torch.einsum('btc,ce->bte', token_tensor, model.router_w),
    )
    assert isinstance(router_logits, torch.Tensor)
    router_logits_flat = router_logits.view(-1, n_experts)

    topk_values, topk_indices = timer.run(
        'topk',
        lambda: torch.topk(router_logits_flat.t(), k=capacity, dim=1),
    )
    assert isinstance(topk_values, torch.Tensor)
    assert isinstance(topk_indices, torch.Tensor)

    permutation = topk_indices.reshape(-1)

    is_triton = isinstance(model, (GECTritonMLP, GECTriton1MLP))

    if is_triton:
        expert_tokens = timer.run(
            'gather_triton',
            lambda: triton_gather(
                x_flat,
                permutation,
                num_experts=n_experts,
                capacity=capacity,
            ),
        )
    else:
        gathered = timer.run('gather_index', lambda: x_flat[permutation])
        assert isinstance(gathered, torch.Tensor)
        expert_tokens = gathered.view(n_experts, -1, C)

    assert isinstance(expert_tokens, torch.Tensor)

    mlp_up = timer.run(
        'mlp_up',
        lambda: torch.bmm(expert_tokens, model.weight1.transpose(1, 2)) + model.bias1.unsqueeze(1),
    )
    assert isinstance(mlp_up, torch.Tensor)

    activated = timer.run('activation', lambda: model.act(mlp_up))
    assert isinstance(activated, torch.Tensor)

    mlp_down = timer.run(
        'mlp_down',
        lambda: torch.bmm(activated, model.weight2.transpose(1, 2)) + model.bias2.unsqueeze(1),
    )
    assert isinstance(mlp_down, torch.Tensor)

    weights = timer.run(
        'sigmoid',
        (lambda: torch.sigmoid(topk_values).reshape(-1))
        if is_triton
        else (lambda: torch.sigmoid(topk_values).view(-1, 1)),
    )
    assert isinstance(weights, torch.Tensor)

    if is_triton:
        scatter_out = timer.run(
            'scatter_triton',
            lambda: triton_scatter(
                mlp_down,
                permutation,
                n_experts,
                capacity,
                n_tokens,
                weights,
            ),
        )
        assert isinstance(scatter_out, torch.Tensor)
        output = scatter_out
    else:
        expert_out = mlp_down.view(-1, C)
        weighted = timer.run('apply_weights', lambda: expert_out * weights)
        assert isinstance(weighted, torch.Tensor)

        output = torch.zeros_like(x_flat)

        def scatter() -> torch.Tensor:
            output.index_add_(0, permutation, weighted)
            return output

        timer.run('scatter', scatter)

    token_counts = timer.run(
        'bincount',
        lambda: torch.bincount(permutation, minlength=n_tokens).to(output.dtype),
    )
    assert isinstance(token_counts, torch.Tensor)

    timer.run(
        'normalize',
        lambda: output.div_(token_counts.clamp(min=1e-6).unsqueeze(-1)),
    )

    return timer.summary()


def build_model(config, impl: str) -> GECMLP | GECMLPReference | GECTritonMLP | GECTriton1MLP:
    model_cfg = ModelConfig(
        model_type='gec',
        n_embd=config.hidden,
        n_experts=config.num_experts,
        expert_dim=config.hidden * 2,
        density=config.density,
    )
    if impl == 'gec-reference':
        model = GECMLPReference(model_cfg)
    elif impl == 'gec-triton':
        model = GECTritonMLP(model_cfg)
    elif impl == 'gec-triton1':
        model = GECTriton1MLP(model_cfg)
    else:
        model = GECMLP(model_cfg)
    return model.to(device=config.device, dtype=torch.bfloat16)


def main() -> None:
    setup_environment()

    parser = argparse.ArgumentParser(description='Inspect GEC forward latency by section')
    add_standard_args(parser)
    add_routing_args(parser)
    parser.add_argument('--impl', default='gec', choices=['gec', 'gec-reference', 'gec-triton', 'gec-triton1'])
    args = parser.parse_args()

    config = args_to_config(args)
    if config.num_tokens % 1024 != 0:
        raise ValueError('num_tokens must be a multiple of 1024 to derive batch size in this inspector')

    B = config.num_tokens // 1024
    T = 1024
    C = config.hidden

    model = build_model(config, args.impl)

    # Always use mixed precision (BF16 autocast)
    autocast_ctx = torch.autocast(device_type='cuda', dtype=torch.bfloat16)

    torch.manual_seed(0)
    token_tensor = torch.randn(B, T, C, device=config.device, dtype=torch.bfloat16)

    warmup = config.warmup
    repeats = config.repeats

    with torch.inference_mode():
        with autocast_ctx:
            for _ in range(warmup):
                inspect_once(model, token_tensor, config.density)

        aggregated = defaultdict(list)
        with torch.inference_mode():
            with autocast_ctx:
                for _ in range(repeats):
                    times = inspect_once(model, token_tensor, config.density)
                    for name, value in times.items():
                        aggregated[name].append(value)

    averages = {name: sum(values) / len(values) for name, values in aggregated.items()}
    total = sum(averages.values())

    print('Section timings (ms):')
    for name in sorted(averages, key=lambda n: -averages[n]):
        print(f'  {name:<15} {averages[name]:6.3f}')
    print(f'  {"total":<15} {total:6.3f}')


if __name__ == '__main__':
    main()
