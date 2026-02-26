"""Gather benchmark comparing torch and Triton kernels."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import torch

from benchmark.permutation.base import BaseKernelBenchmark
from benchmark.permutation.common import BenchmarkResult, format_results, format_stats
from benchmark.permutation.core import BenchmarkConfig, add_standard_args, args_to_config, setup_environment
from src import kernels as balanced_kernels


class GatherForwardBenchmark(BaseKernelBenchmark):
    """Benchmark for gather kernel (forward only, no weights)."""

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__(config)
        self.x: Optional[torch.Tensor] = None

    def setup_data(self) -> None:
        """Setup input tensors."""
        self.setup_common_data()
        self.x = torch.randn(
            (self.config.num_tokens, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

    def create_implementations(self) -> Dict[str, Tuple[Callable[[], None], Callable, Dict[str, float | bool]]]:
        """Create gather implementations (all with no weights, all test raw and compiled)."""
        implementations = {}

        # 1. torch baseline - simple indexing, no weights
        def torch_kernel(tokens: torch.Tensor, routing: torch.Tensor) -> torch.Tensor:
            return tokens[routing].view(
                self.config.num_experts, self.config.capacity, self.config.hidden
            )

        def torch_runner() -> None:
            torch_kernel(self.x, self.indices)

        def torch_output() -> torch.Tensor:
            return torch_kernel(self.x, self.indices)

        implementations['torch'] = (torch_runner, torch_output, {})

        # 2. torch-compile
        compiled = self.compile_manager.try_compile(torch_kernel)
        if compiled is not None:
            def compiled_runner() -> None:
                compiled(self.x, self.indices)

            def compiled_output() -> torch.Tensor:
                return compiled(self.x, self.indices)

            implementations['torch-compile'] = (compiled_runner, compiled_output, {'compiled': True})

        # 3. triton - from src/kernels/balanced.py
        def triton_impl() -> torch.Tensor:
            return balanced_kernels.gather(
                self.x,
                self.indices,
                num_experts=self.config.num_experts,
                capacity=self.config.capacity,
                weights=None,  # No weights
            )

        def triton_runner() -> None:
            triton_impl()

        implementations['triton'] = (triton_runner, triton_impl, {'triton': True})

        # 4. triton-compile
        triton_compiled = self.compile_manager.try_compile(triton_impl)
        if triton_compiled is not None:
            def triton_compiled_runner() -> None:
                triton_compiled()

            implementations['triton-compile'] = (triton_compiled_runner, triton_compiled, {'triton': True, 'compiled': True})

        return implementations

    def compute_bytes(self) -> float:
        """Compute bandwidth for gather operation."""
        return 2 * self.config.num_experts * self.config.capacity * self.config.hidden * self.x.element_size()

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics."""
        # No weights, no stats to report
        return {}
