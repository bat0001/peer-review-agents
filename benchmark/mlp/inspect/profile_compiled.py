"""Profile GEC/GEC_shared MLPs and engine backends under torch.compile."""

from __future__ import annotations

import argparse
from typing import Callable, Tuple

import torch
import torch.nn as nn

from benchmark.mlp.core import add_routing_args, add_standard_args, args_to_config, setup_environment
from benchmark.mlp.engine_utils import init_engine_weights
from benchmark.mlp.engine_wrapper import EngineWithScatter
from src.models.engines import ExpertEngine
from src.models.gec import GECMLP
from src.models.gec_shared import GECSharedMLP
from src.models.model_base import ModelConfig
from src.ops.scatter_backends import get_scatter


IMPLEMENTATIONS = {
    'gec': GECMLP,
    'gec_shared': GECSharedMLP,
}


def build_model(name: str, config, *, is_shared: bool) -> torch.nn.Module:
    """Construct model/engine wrapper matching current model implementations."""
    routing_mode = getattr(config, 'routing_mode', 'topk')

    # Engine-based implementations (index_add vs CSR scatter backends)
    if name in ['index_add', 'index_add_fp32', 'csr', 'csr_optimized']:
        model_type = 'gec_shared' if is_shared else 'gec'
        mc = ModelConfig(
            model_type=model_type,
            n_embd=config.hidden,
            granularity=config.granularity,
            expansion=config.expansion,
            router_activation='sigmoid',
            routing_mode=routing_mode,
        )
        if model_type == 'gec_shared':
            mc.n_experts = mc.granularity * mc.expansion + 1

        n_routed = mc.n_experts if model_type == 'gec' else mc.n_experts - 1
        engine = ExpertEngine(mc, n_routed_experts=n_routed)
        init_engine_weights(engine)

        # Get scatter backend
        scatter = get_scatter(name, max_fanout=mc.n_experts)

        wrapper = EngineWithScatter(engine, scatter, routing_mode, is_shared)
        return wrapper.to(device=config.device, dtype=torch.bfloat16)

    # MLP implementations
    model_type = 'gec_shared' if name == 'gec_shared' else 'gec'
    n_experts = None if model_type == 'gec_shared' else config.num_experts

    model_cfg = ModelConfig(
        model_type=model_type,
        n_embd=config.hidden,
        n_experts=n_experts,
        granularity=config.granularity,
        expansion=config.expansion,
        router_activation='sigmoid',
        routing_mode=routing_mode,
        density=config.density,
    )
    model = IMPLEMENTATIONS[name](model_cfg)
    return model.to(device=config.device, dtype=torch.bfloat16)


def time_callable(fn: Callable[[], Tuple[torch.Tensor, dict]], repeats: int) -> float:
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)

    torch.cuda.synchronize()
    start.record()
    for _ in range(repeats):
        fn()
    end.record()
    torch.cuda.synchronize()

    return float(start.elapsed_time(end)) / repeats


def main() -> None:
    setup_environment()

    parser = argparse.ArgumentParser(description='Profile compiled GEC variants')
    add_standard_args(parser)
    add_routing_args(parser)
    parser.add_argument(
        '--impl',
        default='gec',
        choices=list(IMPLEMENTATIONS.keys()) + ['index_add', 'index_add_fp32', 'csr', 'csr_optimized'],
        help='which implementation to profile (mlp or engine backends)',
    )
    parser.add_argument('--compile-mode', default='default', help='torch.compile mode')
    parser.add_argument('--profile-steps', type=int, default=5, help='steps to record in profiler')
    parser.add_argument(
        '--is-shared',
        action='store_true',
        help='Use shared-expert capacity/normalization (gec_shared style) for engine or select shared MLP.',
    )
    args = parser.parse_args()

    config = args_to_config(args)
    if config.num_tokens % 1024 != 0:
        raise ValueError('num_tokens must be a multiple of 1024 to derive batch size')

    B = config.num_tokens // 1024
    T = 1024
    C = config.hidden

    model = build_model(args.impl, config, is_shared=args.is_shared)
    model.eval()

    compiled_model = torch.compile(model, mode=args.compile_mode)

    # Always use mixed precision (BF16 autocast)
    autocast_ctx = torch.autocast(device_type='cuda', dtype=torch.bfloat16)

    torch.manual_seed(0)
    tokens = torch.randn(B, T, C, device=config.device, dtype=torch.bfloat16)

    def forward_call():
        with autocast_ctx:
            return compiled_model(tokens)

    # Warmup compiled graph
    for _ in range(config.warmup):
        forward_call()
    torch.cuda.synchronize()

    avg_ms = time_callable(forward_call, config.repeats)
    print(f'Average compiled forward: {avg_ms:.3f} ms over {config.repeats} repeats')

    profile_steps = args.profile_steps
    with torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA],
        record_shapes=False,
        profile_memory=False,
    ) as prof:
        for _ in range(profile_steps):
            forward_call()
    torch.cuda.synchronize()

    print('\nCUDA kernels during compiled forward:')
    print(prof.key_averages().table(sort_by='self_cuda_time_total', row_limit=-1))


if __name__ == '__main__':
    main()
