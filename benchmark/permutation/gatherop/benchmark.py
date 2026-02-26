"""Gather autograd benchmark comparing forward/backward performance."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import torch

from benchmark.permutation.base import BaseAutogradBenchmark
from benchmark.permutation.common import BenchmarkResult, format_results, format_stats
from benchmark.permutation.core import BenchmarkConfig, add_standard_args, args_to_config, setup_environment

from src import kernels as balanced_kernels
from src.ops import gather as gather_op
from src.ops.csr import csr_gather


class GatherBackwardBenchmark(BaseAutogradBenchmark):
    """Benchmark for gather autograd operation (forward+backward, no weights)."""

    def __init__(self, config: BenchmarkConfig) -> None:
        """Initialize gather backward benchmark (forward+backward only, no weights)."""
        super().__init__(config)
        self.x_template: Optional[torch.Tensor] = None
        self.loss_weights: Optional[torch.Tensor] = None
        self.indices_csr: Optional[torch.Tensor] = None
        self.slot_indices: Optional[torch.Tensor] = None
        self.slot_offsets: Optional[torch.Tensor] = None
        self.slot_counts: Optional[torch.Tensor] = None
        self.max_fanout: int = config.num_experts

    def setup_data(self) -> None:
        """Setup input tensors and loss weights."""
        self.setup_indices()

        self.x_template = torch.randn(
            (self.config.num_tokens, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )
        self.loss_weights = torch.randn(
            (self.config.num_experts, self.config.capacity, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

        assert self.indices is not None
        indices_2d = self.indices.view(self.config.num_experts, self.config.capacity)
        self.indices_csr = indices_2d.to(torch.int32).contiguous()
        slot_idx, slot_offs, slot_counts = balanced_kernels.build_slot_indices(
            self.indices_csr,
            num_tokens=self.config.num_tokens,
            max_experts=self.max_fanout,
        )
        self.slot_indices = slot_idx
        self.slot_offsets = slot_offs
        self.slot_counts = slot_counts

    def create_implementations(self) -> Dict[str, Tuple[Callable, Callable, Dict[str, float | bool]]]:
        """Create forward+backward implementations (no weights, all test raw and compiled)."""
        return self._create_forward_backward_implementations()

    def _create_forward_backward_implementations(self) -> Dict[str, Tuple[Callable, Callable, Dict[str, float | bool]]]:
        """Create forward+backward implementations (no weights, all test raw and compiled)."""
        implementations = {}

        # 1. torch baseline - simple indexing, no weights
        def torch_forward(tokens: torch.Tensor) -> torch.Tensor:
            return tokens[self.indices].view(
                self.config.num_experts, self.config.capacity, self.config.hidden
            )

        implementations['torch'] = self.make_autograd_case(
            torch_forward,
            loss_weights=self.loss_weights,
            input_template=self.x_template,
        )

        # 2. torch-compile
        if hasattr(torch, 'compile'):
            compiled = self.compile_manager.try_compile(torch_forward)
            if compiled is not None:
                compiled_case = self.make_autograd_case(
                    compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.x_template,
                )
                compiled_case[0]()
                torch.cuda.synchronize()
                implementations['torch-compile'] = (
                    compiled_case[0],
                    compiled_case[1],
                    {'compiled': True},
                )

        # 3. balanced-op (custom gather op, no weights)
        def triton_forward(tokens: torch.Tensor) -> torch.Tensor:
            return gather_op(
                tokens,
                self.indices,
                num_experts=self.config.num_experts,
                capacity=self.config.capacity,
            )

        implementations['balanced-op'] = self.make_autograd_case(
            triton_forward,
            loss_weights=self.loss_weights,
            input_template=self.x_template,
            extras={'triton': True},
        )

        # 4. balanced-op-compile
        if hasattr(torch, 'compile'):
            triton_compiled = self.compile_manager.try_compile(triton_forward)
            if triton_compiled is not None:
                triton_compiled_case = self.make_autograd_case(
                    triton_compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.x_template,
                )
                triton_compiled_case[0]()
                torch.cuda.synchronize()
                implementations['balanced-op-compile'] = (
                    triton_compiled_case[0],
                    triton_compiled_case[1],
                    {'triton': True, 'compiled': True},
                )

        # 5. CSR gather autograd
        def csr_forward(tokens: torch.Tensor) -> torch.Tensor:
            assert self.indices_csr is not None
            assert self.slot_indices is not None
            assert self.slot_offsets is not None
            assert self.slot_counts is not None
            return csr_gather(
                tokens,
                self.indices_csr,
                max_experts=self.max_fanout,
                slot_indices=self.slot_indices,
                slot_offsets=self.slot_offsets,
                slot_counts=self.slot_counts,
            )

        implementations['csr'] = self.make_autograd_case(
            csr_forward,
            loss_weights=self.loss_weights,
            input_template=self.x_template,
            extras={'csr': True},
        )

        if hasattr(torch, 'compile'):
            csr_compiled = self.compile_manager.try_compile(csr_forward)
            if csr_compiled is not None:
                csr_compiled_case = self.make_autograd_case(
                    csr_compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.x_template,
                )
                csr_compiled_case[0]()
                torch.cuda.synchronize()
                implementations['csr-compile'] = (
                    csr_compiled_case[0],
                    csr_compiled_case[1],
                    {'csr': True, 'compiled': True},
                )

        return implementations

    def compute_bytes(self) -> float:
        """Compute total bytes for forward+backward."""
        dtype_size = 2  # BF16 (always used via mixed precision autocast)

        # Forward: read tokens, write expert_out
        forward_bytes = 2 * self.config.num_experts * self.config.capacity * self.config.hidden * dtype_size

        # Backward: read grad_output, write grad_input
        backward_bytes = (
            2 * self.config.num_experts * self.config.capacity * self.config.hidden
            + self.config.num_tokens * self.config.hidden
        ) * dtype_size

        return forward_bytes + backward_bytes

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics."""
        if self.loss_weights is not None:
            return {
                'loss_grad': {
                    'min': float(self.loss_weights.min()),
                    'max': float(self.loss_weights.max()),
                    'mean': float(self.loss_weights.mean()),
                    'std': float(self.loss_weights.std()),
                }
            }
        return {}
