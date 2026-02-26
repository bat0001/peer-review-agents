"""Backward pass benchmarks for ExpertEngine.

Benchmarks routing modes (topk and threshold) for ExpertEngine forward+backward
with different scatter backends.

Tests recipes (combinations of scatter × engine × wrapper × compile):
- index_add: PyTorch index_add_ scatter
- index_add-compiled: torch.compile version
- csr: CSR kernel scatter
- csr-compiled: torch.compile version

Note: Threshold mode with gradients is used during training when threshold_warmup_steps
is enabled (dual-path training scenario).

Usage:
    python -m benchmark.mlp backward --routing-mode topk
    python -m benchmark.mlp backward --routing-mode threshold
"""

from __future__ import annotations

import argparse
from typing import Dict, Tuple

import torch
import torch.nn as nn

from src.models.model_base import ModelConfig
from src.models.engines import ExpertEngine
from src.ops.scatter_backends import get_scatter

from .base import MLPAutogradBenchmark
from .common import format_grouped_results
from .core import add_routing_args, add_standard_args, args_to_config, setup_environment
from .engine_utils import (
    init_engine_weights,
    warmup_threshold_cutoffs,
    get_is_shared_list,
    get_implementation_groups,
    shared_label,
)
from .engine_wrapper import EngineWithScatter


class ExpertEngineBackward(MLPAutogradBenchmark):
    """Benchmark ExpertEngine forward+backward with configurable routing mode."""

    def __init__(self, config, routing_mode: str = 'topk'):
        """Initialize backward benchmark.

        Args:
            config: Benchmark configuration
            routing_mode: 'topk' or 'threshold'
        """
        super().__init__(config)
        self.routing_mode = routing_mode

        if routing_mode not in ['topk', 'threshold']:
            raise ValueError(f"routing_mode must be 'topk' or 'threshold', got {routing_mode}")

    def setup_data(self):
        """Setup engine, scatter backends, and input data."""
        # Input tensor (B, T, C)
        B = max(1, self.config.num_tokens // 1024)
        T = 1024
        C = self.config.hidden
        self.input_tensor = torch.randn(B, T, C, device=self.device, dtype=torch.bfloat16)

        # Model config
        mc = ModelConfig(
            n_embd=C,
            n_experts=self.config.num_experts,
            granularity=self.config.granularity,
            expansion=self.config.expansion,
            router_activation='sigmoid',
            normalization_mode='fanout',
        )

        # Single engine (weights shared across all scatter backend tests)
        self.engine = ExpertEngine(mc, n_routed_experts=mc.n_experts).to(self.device, dtype=torch.bfloat16)
        init_engine_weights(self.engine)

        # Create scatter backends
        self.scatter_index_add = get_scatter('index_add')
        self.scatter_csr = get_scatter('csr', max_fanout=mc.n_experts)
        self.scatter_csr_optimized = get_scatter('csr_optimized', max_fanout=mc.n_experts)

        # Set mode based on routing
        if self.routing_mode == 'topk':
            self.engine.train()
        else:  # threshold
            # Warmup: populate cutoff EMAs with topk iterations
            warmup_threshold_cutoffs(self.engine, self.input_tensor)
            # Threshold mode can be used during training (dual-path)
            # Keep in train mode to allow gradients
            self.engine.train()

    def create_autograd_implementations(self) -> Dict[str, Tuple[nn.Module, Dict]]:
        """Create autograd implementations for all recipes."""
        # Compute bytes (3x for forward + backward + gradient)
        bytes_moved = self.compute_bytes()

        impls = {}

        # Determine which configs to test based on gec_config flag
        gec_config = getattr(self.config, 'gec_config', 'all')
        is_shared_list = get_is_shared_list(gec_config)

        # Test each scatter backend × is_shared combination
        scatter_backends = [
            ('index_add', self.scatter_index_add),
            ('csr', self.scatter_csr),
            ('csr_optimized', self.scatter_csr_optimized),
        ]

        for scatter_name, scatter in scatter_backends:
            for is_shared in is_shared_list:
                label = shared_label(is_shared)
                name = f'{scatter_name}-{label}'

                # Create wrapper module
                wrapper = EngineWithScatter(self.engine, scatter, self.routing_mode, is_shared)
                impls[name] = (wrapper, {'bytes': bytes_moved})

                # Add torch.compile version
                self._add_compiled_version(impls, scatter, is_shared, name, bytes_moved)

        return impls

    def _add_compiled_version(self, impls: Dict, scatter, is_shared: bool, base_name: str, bytes_moved: float):
        """Add torch.compile version of the implementation."""
        wrapper = EngineWithScatter(self.engine, scatter, self.routing_mode, is_shared)

        # Try to compile the wrapper module
        compiled = self.compile_manager.try_compile(wrapper)
        if compiled is not None:
            # Extra warmup run to ensure compilation happens before measurement
            input_copy = self.input_tensor.clone().requires_grad_(True)
            with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
                out = compiled(input_copy)
                if isinstance(out, tuple):
                    out = out[0]
                loss = out.sum()
            loss.backward()
            torch.cuda.synchronize()

            compiled_name = f'{base_name}-compiled'
            impls[compiled_name] = (compiled, {'bytes': bytes_moved, 'compiled': True})

    def create_implementations(self):
        """Delegate to create_autograd_implementations (required by base class)."""
        return self.create_autograd_implementations()

    def compute_bytes(self) -> float:
        """Compute total bytes moved for forward + backward.

        Includes:
        - Forward: input read, output write, weight reads
        - Backward: gradient reads/writes, weight gradient accumulation

        Approximate as 3x forward pass.
        """
        B, T, C = self.input_tensor.shape
        n_tokens = B * T

        # Forward pass estimate
        io_bytes = n_tokens * C * 2 * 2  # 2 tensors × 2 bytes (bfloat16)
        expert_dim = C // self.config.expansion
        weight_bytes = (
            self.config.num_experts *
            (expert_dim * C + C * expert_dim) *
            2  # bfloat16
        )
        forward_bytes = io_bytes + weight_bytes

        # Backward is roughly 2x forward (gradients + weight grads)
        return float(3.0 * forward_bytes)

    def get_implementation_groups(self) -> Dict[str, list]:
        """Define validation groups: CSR and compiled versions validate against index_add."""
        gec_config = getattr(self.config, 'gec_config', 'all')
        return get_implementation_groups(gec_config)


def main():
    """Main entry point for backward benchmarks."""
    parser = argparse.ArgumentParser(description='ExpertEngine forward+backward benchmark')
    add_standard_args(parser)
    add_routing_args(parser)

    args = parser.parse_args()
    config = args_to_config(args)
    setup_environment()

    # Create and run benchmark
    benchmark = ExpertEngineBackward(config, routing_mode=args.routing_mode)
    results, stats = benchmark.run_autograd_case()

    # Format and print results
    groups = benchmark.get_implementation_groups()
    print(format_grouped_results(results, groups))

    # Print summary
    print(f"\nBenchmark: ExpertEngine forward+backward ({args.routing_mode})")
    print(f"Configuration: {config.num_tokens} tokens, {config.hidden} hidden, "
          f"{config.num_experts} experts, G={config.granularity}, E={config.expansion}")


if __name__ == '__main__':
    main()
