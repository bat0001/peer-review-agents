"""Scatter op benchmark (forward+backward autograd, with weights)."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import torch

from benchmark.permutation.base import BaseAutogradBenchmark
from benchmark.permutation.common import BenchmarkResult, format_results, format_stats, measure
from benchmark.permutation.core import BenchmarkConfig
from src import kernels as balanced_kernels
from src.ops.scatter import scatter as scatter_op
from src.ops.csr import csr_scatter_sum
from src.ops.csr_optimized import csr_scatter_sum_optimized


class ScatterBackwardBenchmark(BaseAutogradBenchmark):
    """Benchmark for scatter autograd operation (forward+backward, with weights).

    Always computes weight gradients.
    """

    def __init__(self, config: BenchmarkConfig) -> None:
        """Initialize scatter backward benchmark (forward+backward only, always with weights)."""
        super().__init__(config)

        # Input data
        self.expert_template: Optional[torch.Tensor] = None
        self.loss_weights: Optional[torch.Tensor] = None

        # CSR data
        self.indices_2d: Optional[torch.Tensor] = None
        self.slot_indices: Optional[torch.Tensor] = None
        self.slot_offsets: Optional[torch.Tensor] = None
        self.slot_counts: Optional[torch.Tensor] = None
        self.max_experts: int = config.granularity * config.expansion

    def setup_data(self) -> None:
        """Setup data for forward+backward testing."""
        # Generate routing indices (expert-major topk)
        scores = torch.randn(
            (self.config.num_experts, self.config.num_tokens),
            dtype=torch.float32,
            device=self.device,
        )
        self.indices = torch.topk(
            scores, k=self.config.capacity, dim=1, largest=True, sorted=True
        ).indices.reshape(-1)
        self.weights = torch.sigmoid(
            torch.randn(self.indices.shape[0], dtype=torch.float32, device=self.device)
        ).requires_grad_(True)

        # Expert output template
        self.expert_template = torch.randn(
            (self.config.num_experts, self.config.capacity, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

        # Loss gradient weights (for computing loss from forward output)
        self.loss_weights = torch.randn(
            (self.config.num_tokens, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

        # Build CSR format for CSR scatter kernel
        self.indices_2d = self.indices.view(self.config.num_experts, self.config.capacity)
        self.slot_indices, self.slot_offsets, self.slot_counts = balanced_kernels.build_slot_indices(
            self.indices_2d.to(torch.int32).contiguous(),
            num_tokens=self.config.num_tokens,
            max_experts=self.max_experts
        )

    def create_implementations(self) -> Dict[str, Tuple[Callable, Callable, Dict[str, float | bool]]]:
        """Create forward+backward implementations (all with weights, all test raw and compiled)."""
        implementations = {}

        # ============================================================================
        # 1. torch (REFERENCE - FP32 accumulation, matches Triton kernel semantics)
        # ============================================================================
        def torch_forward(expert_tensor: torch.Tensor) -> torch.Tensor:
            weighted = torch.mul(
                expert_tensor.view(-1, self.config.hidden),
                self.weights.view(-1, 1)
            ).to(torch.float32)
            accumulator = torch.zeros(
                (self.config.num_tokens, self.config.hidden),
                dtype=torch.float32,
                device=expert_tensor.device
            )
            accumulator.index_add_(0, self.indices, weighted)
            return accumulator.to(torch.bfloat16)

        implementations['torch'] = self.make_autograd_case(
            torch_forward,
            loss_weights=self.loss_weights,
            input_template=self.expert_template,
        )

        # ============================================================================
        # 1b. torch-bf16 (native BF16 accumulation - shows PyTorch default behavior)
        # ============================================================================
        def torch_bf16_forward(expert_tensor: torch.Tensor) -> torch.Tensor:
            weighted = torch.mul(
                expert_tensor.view(-1, self.config.hidden),
                self.weights.view(-1, 1)
            )
            accumulator = torch.zeros(
                (self.config.num_tokens, self.config.hidden),
                dtype=torch.bfloat16,
                device=expert_tensor.device
            )
            accumulator.index_add_(0, self.indices, weighted.to(accumulator.dtype))
            return accumulator

        implementations['torch-bf16'] = self.make_autograd_case(
            torch_bf16_forward,
            loss_weights=self.loss_weights,
            input_template=self.expert_template,
        )

        # ============================================================================
        # 2. torch-compile (FP32 accumulation)
        # ============================================================================
        if hasattr(torch, 'compile'):
            compiled = self.compile_manager.try_compile(torch_forward)
            if compiled is not None:
                compiled_case = self.make_autograd_case(
                    compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.expert_template,
                )
                compiled_case[0]()
                torch.cuda.synchronize()
                implementations['torch-compile'] = (
                    compiled_case[0],
                    compiled_case[1],
                    {'compiled': True},
                )

        # ============================================================================
        # 2b. torch-bf16-compile (BF16 accumulation)
        # ============================================================================
        if hasattr(torch, 'compile'):
            compiled_bf16 = self.compile_manager.try_compile(torch_bf16_forward)
            if compiled_bf16 is not None:
                compiled_bf16_case = self.make_autograd_case(
                    compiled_bf16,
                    loss_weights=self.loss_weights,
                    input_template=self.expert_template,
                )
                compiled_bf16_case[0]()
                torch.cuda.synchronize()
                implementations['torch-bf16-compile'] = (
                    compiled_bf16_case[0],
                    compiled_bf16_case[1],
                    {'compiled': True},
                )

        # ============================================================================
        # 3. balanced-op (custom scatter op with fused backward, uses triton-atomic)
        # ============================================================================
        def scatter_forward(expert_tensor: torch.Tensor) -> torch.Tensor:
            # Closure over self.indices, self.weights, and config params
            return scatter_op(
                expert_tensor,
                self.indices,
                self.config.num_experts,
                self.config.capacity,
                self.config.num_tokens,
                self.weights,
            )

        implementations['balanced-op'] = self.make_autograd_case(
            scatter_forward,
            loss_weights=self.loss_weights,
            input_template=self.expert_template,
            extras={'triton': True},
        )

        # ============================================================================
        # 4. balanced-op-compile
        # ============================================================================
        if hasattr(torch, 'compile'):
            scatter_compiled = self.compile_manager.try_compile(scatter_forward)
            if scatter_compiled is not None:
                scatter_compiled_case = self.make_autograd_case(
                    scatter_compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.expert_template,
                )
                scatter_compiled_case[0]()
                torch.cuda.synchronize()
                implementations['balanced-op-compile'] = (
                    scatter_compiled_case[0],
                    scatter_compiled_case[1],
                    {'triton': True, 'compiled': True},
                )

        # ============================================================================
        # 5. csr-scatter-op (CSR scatter autograd, token-parallel forward)
        # ============================================================================
        def csr_scatter_forward(expert_tensor: torch.Tensor) -> torch.Tensor:
            # Flatten expert tensor for CSR scatter
            expert_flat = expert_tensor.view(-1, self.config.hidden)
            return csr_scatter_sum(
                expert_flat,
                self.indices_2d,
                self.config.num_tokens,
                self.max_experts,
                self.slot_indices,
                self.slot_offsets,
                self.slot_counts,
                weights_flat=self.weights,
            )

        implementations['csr-scatter-op'] = self.make_autograd_case(
            csr_scatter_forward,
            loss_weights=self.loss_weights,
            input_template=self.expert_template,
            extras={'triton': True, 'token_parallel': True},
        )

        # ============================================================================
        # 6. csr-scatter-op-compile
        # ============================================================================
        if hasattr(torch, 'compile'):
            csr_compiled = self.compile_manager.try_compile(csr_scatter_forward)
            if csr_compiled is not None:
                csr_compiled_case = self.make_autograd_case(
                    csr_compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.expert_template,
                )
                csr_compiled_case[0]()
                torch.cuda.synchronize()
                implementations['csr-scatter-op-compile'] = (
                    csr_compiled_case[0],
                    csr_compiled_case[1],
                    {'triton': True, 'token_parallel': True, 'compiled': True},
                )

        # ============================================================================
        # 7. csr-optimized-op (CSR scatter with optimized backward kernel)
        # ============================================================================
        def csr_optimized_forward(expert_tensor: torch.Tensor) -> torch.Tensor:
            expert_flat = expert_tensor.view(-1, self.config.hidden)
            return csr_scatter_sum_optimized(
                expert_flat,
                self.indices_2d,
                self.config.num_tokens,
                self.max_experts,
                self.slot_indices,
                self.slot_offsets,
                self.slot_counts,
                weights=self.weights,
                add_into_tensor=None,
            )

        implementations['csr-optimized-op'] = self.make_autograd_case(
            csr_optimized_forward,
            loss_weights=self.loss_weights,
            input_template=self.expert_template,
            extras={'triton': True, 'token_parallel': True, 'optimized_bwd': True},
        )

        # ============================================================================
        # 8. csr-optimized-op-compile
        # ============================================================================
        if hasattr(torch, 'compile'):
            csr_opt_compiled = self.compile_manager.try_compile(csr_optimized_forward)
            if csr_opt_compiled is not None:
                csr_opt_compiled_case = self.make_autograd_case(
                    csr_opt_compiled,
                    loss_weights=self.loss_weights,
                    input_template=self.expert_template,
                )
                csr_opt_compiled_case[0]()
                torch.cuda.synchronize()
                implementations['csr-optimized-op-compile'] = (
                    csr_opt_compiled_case[0],
                    csr_opt_compiled_case[1],
                    {'triton': True, 'token_parallel': True, 'optimized_bwd': True, 'compiled': True},
                )

        return implementations

    def compute_bytes(self) -> float:
        """Compute bytes moved for forward+backward."""
        dtype_size = 2  # BF16

        # Forward: read expert outputs + weights, write token outputs
        forward_bytes = (
            self.config.num_experts * self.config.capacity * self.config.hidden  # expert outputs
            + self.config.num_experts * self.config.capacity  # weights
            + self.config.num_tokens * self.config.hidden  # token outputs
        ) * dtype_size

        # Backward: read grad_output, write grad_expert + grad_weights
        backward_bytes = (
            self.config.num_tokens * self.config.hidden  # grad_output
            + self.config.num_experts * self.config.capacity * self.config.hidden  # grad_expert
            + self.config.num_experts * self.config.capacity  # grad_weights
        ) * dtype_size

        return forward_bytes + backward_bytes

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics."""
        weights = self.weights.detach()
        return {
            'weights': {
                'min': float(weights.min()),
                'max': float(weights.max()),
                'mean': float(weights.mean()),
                'std': float(weights.std()),
            },
            'loss_grad': {
                'min': float(self.loss_weights.min()),
                'max': float(self.loss_weights.max()),
                'mean': float(self.loss_weights.mean()),
                'std': float(self.loss_weights.std()),
            },
        }
