"""Scatter AddInto benchmarks (mimics GEC_shared pattern).

AddInto scatter accumulates routed expert outputs INTO a pre-existing buffer
(the weighted shared expert output) rather than scattering into zeros.
This is the key fusion optimization for GEC_shared.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import torch

from benchmark.permutation.base import BaseKernelBenchmark, BaseAutogradBenchmark
from benchmark.permutation.core import BenchmarkConfig
from benchmark.permutation.scatter.benchmark import build_inverse_indices
from src import kernels as balanced_kernels
from src.kernels.sequential import _sequential_add
from src.ops.csr import csr_scatter_sum
from src.ops.csr_optimized import csr_scatter_sum_optimized


class ScatterAddIntoForwardBenchmark(BaseKernelBenchmark):
    """Benchmark for scatter kernel with add_into (forward only, with weights).

    Mimics GEC_shared pattern: accumulate routed outputs into pre-existing buffer.

    Implementations:
    - torch (reference): clone + index_add
    - csr-addinto: CSR kernel with ACCUMULATE=1
    - sequential-addinto: Sequential kernel with ADD_INTO=True
    """

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__(config)
        self.expert_out: Optional[torch.Tensor] = None
        self.expert_out_flat: Optional[torch.Tensor] = None
        self.weights_flat_fp32: Optional[torch.Tensor] = None
        self.max_experts: int = config.granularity * config.expansion  # G * E

        # Pre-existing buffer (mimics weighted shared expert output)
        self.shared_out: Optional[torch.Tensor] = None

        # For sequential kernel
        self.inverse_indices: Optional[torch.Tensor] = None

        # For CSR kernel
        self.indices_2d: Optional[torch.Tensor] = None
        self.slot_indices: Optional[torch.Tensor] = None
        self.slot_offsets: Optional[torch.Tensor] = None
        self.slot_counts: Optional[torch.Tensor] = None

    def setup_data(self) -> None:
        """Setup scatter addinto input tensors."""
        self.setup_common_data()

        # Routed expert outputs
        self.expert_out = torch.randn(
            (self.config.num_experts, self.config.capacity, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )
        self.expert_out_flat = self.expert_out.view(-1, self.config.hidden)
        self.weights_flat_fp32 = self.weights.view(-1, 1)

        # Pre-existing buffer (mimics weighted shared expert output)
        self.shared_out = torch.randn(
            (self.config.num_tokens, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

        # Build inverse indices for sequential kernel
        self.inverse_indices = build_inverse_indices(
            self.indices, self.config.num_tokens, self.max_experts
        )

        # Build CSR format for CSR kernel
        self.indices_2d = self.indices.view(self.config.num_experts, self.config.capacity)
        from src.kernels.csr import build_slot_indices
        self.slot_indices, self.slot_offsets, self.slot_counts = build_slot_indices(
            self.indices_2d,
            self.config.num_tokens,
            max_experts=self.max_experts
        )

    def create_implementations(self) -> Dict[str, Tuple[Callable[[], None], Callable, Dict[str, float | bool]]]:
        """Create all scatter addinto implementations."""
        implementations = {}

        # ============================================================================
        # 1. torch (REFERENCE - FP32 accumulation, matches Triton kernel semantics)
        # ============================================================================
        def index_add_kernel() -> torch.Tensor:
            out = self.shared_out.float()
            weighted = self.expert_out_flat.float() * self.weights_flat_fp32
            out.index_add_(0, self.indices, weighted)
            return out.to(torch.bfloat16)

        def index_add_runner() -> None:
            index_add_kernel()

        implementations['torch'] = (index_add_runner, index_add_kernel, {'weight_fused': True})

        # ============================================================================
        # 1b. torch-bf16 (native BF16 accumulation - shows PyTorch default behavior)
        # ============================================================================
        def index_add_bf16_kernel() -> torch.Tensor:
            out = self.shared_out.clone()
            weighted = torch.mul(self.expert_out_flat, self.weights_flat_fp32)
            out.index_add_(0, self.indices, weighted.to(out.dtype))
            return out

        def index_add_bf16_runner() -> None:
            index_add_bf16_kernel()

        implementations['torch-bf16'] = (index_add_bf16_runner, index_add_bf16_kernel, {'weight_fused': True})

        # ============================================================================
        # 2. torch-compile (FP32 accumulation)
        # ============================================================================
        compiled = self.compile_manager.try_compile(index_add_kernel)
        if compiled is not None:
            def compiled_runner() -> None:
                compiled()

            implementations['torch-compile'] = (
                compiled_runner, compiled, {'weight_fused': True, 'compiled': True}
            )

        # ============================================================================
        # 2b. torch-bf16-compile (BF16 accumulation)
        # ============================================================================
        compiled_bf16 = self.compile_manager.try_compile(index_add_bf16_kernel)
        if compiled_bf16 is not None:
            def compiled_bf16_runner() -> None:
                compiled_bf16()

            implementations['torch-bf16-compile'] = (
                compiled_bf16_runner, compiled_bf16, {'weight_fused': True, 'compiled': True}
            )

        # ============================================================================
        # 3. sequential-addinto
        # ============================================================================
        def sequential_impl() -> torch.Tensor:
            out = self.shared_out.clone()
            _sequential_add[self.config.num_tokens,](
                self.expert_out_flat,
                out,
                self.inverse_indices,
                self.weights,
                MAX_EXPERTS=self.max_experts,
                NUM_COLUMNS=self.config.hidden,
                SCALE=True,
                ADD_INTO=True,  # Key difference: accumulate into existing buffer
            )
            return out

        def sequential_runner() -> None:
            sequential_impl()

        implementations['sequential-addinto'] = (
            sequential_runner, sequential_impl, {'weight_fused': True}
        )

        # ============================================================================
        # 4. sequential-addinto-compile
        # ============================================================================
        seq_compiled = self.compile_manager.try_compile(sequential_impl)
        if seq_compiled is not None:
            def seq_compiled_runner() -> None:
                seq_compiled()

            implementations['sequential-addinto-compile'] = (
                seq_compiled_runner, seq_compiled, {'weight_fused': True, 'compiled': True}
            )

        # ============================================================================
        # 5. csr-addinto
        # ============================================================================
        from src.kernels.csr import _csr_scatter_sum

        def csr_impl() -> torch.Tensor:
            out = self.shared_out.clone()
            # Launch token-parallel kernel with ACCUMULATE=1
            _csr_scatter_sum[self.config.num_tokens,](
                self.expert_out_flat,
                out,
                self.slot_indices,
                self.slot_offsets,
                self.slot_counts,
                self.weights,
                MAX_EXPERTS=self.max_experts,
                NUM_COLUMNS=self.config.hidden,
                USE_WEIGHTS=1,
                ACCUMULATE=1,  # Key difference: accumulate into existing buffer
                SHARED_EXPERT_WEIGHTS=0,
                shared_expert_weights=out,  # dummy pointer
            )
            return out

        def csr_runner() -> None:
            csr_impl()

        implementations['csr-addinto'] = (
            csr_runner, csr_impl, {'weight_fused': True, 'triton': True, 'token_parallel': True}
        )

        # ============================================================================
        # 6. csr-addinto-compile
        # ============================================================================
        csr_compiled = self.compile_manager.try_compile(csr_impl)
        if csr_compiled is not None:
            def csr_compiled_runner() -> None:
                csr_compiled()

            implementations['csr-addinto-compile'] = (
                csr_compiled_runner, csr_compiled,
                {'weight_fused': True, 'triton': True, 'token_parallel': True, 'compiled': True}
            )

        return implementations

    def compute_bytes(self) -> float:
        """Compute bytes moved for scatter addinto operation."""
        # Read: expert outputs + weights + shared_out (for clone)
        # Write: output buffer
        elem_size = self.expert_out.element_size()
        read_bytes = (
            self.config.num_experts * self.config.capacity * self.config.hidden  # expert outputs
            + self.config.num_tokens * self.config.hidden  # shared_out
        ) * elem_size
        write_bytes = self.config.num_tokens * self.config.hidden * elem_size
        return read_bytes + write_bytes

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics."""
        return {
            'weights': {
                'min': float(self.weights.min()),
                'max': float(self.weights.max()),
                'mean': float(self.weights.mean()),
                'std': float(self.weights.std()),
            },
            'shared_out': {
                'min': float(self.shared_out.min()),
                'max': float(self.shared_out.max()),
                'mean': float(self.shared_out.mean()),
                'std': float(self.shared_out.std()),
            }
        }


class ScatterAddIntoBackwardBenchmark(BaseAutogradBenchmark):
    """Benchmark for scatter addinto autograd (forward+backward, with weights).

    Mimics GEC_shared pattern with full autograd support.
    Tests gradient flow through both routed experts and shared expert.
    """

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__(config)

        # Input data
        self.expert_template: Optional[torch.Tensor] = None
        self.shared_template: Optional[torch.Tensor] = None
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

        # Shared output template (mimics weighted shared expert output)
        self.shared_template = torch.randn(
            (self.config.num_tokens, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

        # Loss gradient weights
        self.loss_weights = torch.randn(
            (self.config.num_tokens, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )

        # Build CSR format
        self.indices_2d = self.indices.view(self.config.num_experts, self.config.capacity)
        self.slot_indices, self.slot_offsets, self.slot_counts = balanced_kernels.build_slot_indices(
            self.indices_2d.to(torch.int32).contiguous(),
            num_tokens=self.config.num_tokens,
            max_experts=self.max_experts
        )

    def create_implementations(self) -> Dict[str, Tuple[Callable, Callable, Dict[str, float | bool]]]:
        """Create forward+backward implementations for addinto pattern."""
        implementations = {}

        # ============================================================================
        # 1. torch (REFERENCE - FP32 accumulation, matches Triton kernel semantics)
        # ============================================================================
        def torch_forward(expert_tensor: torch.Tensor, shared_tensor: torch.Tensor) -> torch.Tensor:
            weighted = torch.mul(
                expert_tensor.view(-1, self.config.hidden),
                self.weights.view(-1, 1)
            ).to(torch.float32)
            accumulator = shared_tensor.to(torch.float32).clone()
            accumulator.index_add_(0, self.indices, weighted)
            return accumulator.to(torch.bfloat16)

        # ============================================================================
        # 1b. torch-bf16 (native BF16 accumulation - shows PyTorch default behavior)
        # ============================================================================
        def torch_bf16_forward(expert_tensor: torch.Tensor, shared_tensor: torch.Tensor) -> torch.Tensor:
            weighted = torch.mul(
                expert_tensor.view(-1, self.config.hidden),
                self.weights.view(-1, 1)
            )
            accumulator = shared_tensor.clone()
            accumulator.index_add_(0, self.indices, weighted.to(accumulator.dtype))
            return accumulator

        # Custom make_autograd_case for two-input forward
        def make_two_input_autograd_case(
            forward_fn: Callable,
            extras: Dict[str, float | bool] = None,
        ) -> Tuple[Callable, Callable, Dict]:
            """Create autograd case for two-input forward (expert + shared).

            Returns (forward_out, combined_grad) where combined_grad = cat(expert_grad.flatten(), shared_grad.flatten())
            to be compatible with base class run_autograd_case which expects 2-tuple output.
            """
            extras = extras or {}

            def runner() -> None:
                # Fresh inputs with gradients
                expert_in = self.expert_template.clone().requires_grad_(True)
                shared_in = self.shared_template.clone().requires_grad_(True)

                # Forward
                out = forward_fn(expert_in, shared_in)

                # Compute scalar loss and backward
                loss = (out * self.loss_weights).sum()
                loss.backward()

            def output_fn() -> Tuple[torch.Tensor, torch.Tensor]:
                # Get outputs for validation
                expert_in = self.expert_template.clone().requires_grad_(True)
                shared_in = self.shared_template.clone().requires_grad_(True)
                out = forward_fn(expert_in, shared_in)
                loss = (out * self.loss_weights).sum()
                loss.backward()
                # Combine both gradients into single tensor for comparison
                combined_grad = torch.cat([expert_in.grad.flatten(), shared_in.grad.flatten()])
                return out.detach(), combined_grad.detach()

            return runner, output_fn, extras

        implementations['torch'] = make_two_input_autograd_case(torch_forward)
        implementations['torch-bf16'] = make_two_input_autograd_case(torch_bf16_forward)

        # ============================================================================
        # 2. torch-compile (FP32 accumulation)
        # ============================================================================
        if hasattr(torch, 'compile'):
            compiled = self.compile_manager.try_compile(torch_forward)
            if compiled is not None:
                case = make_two_input_autograd_case(compiled)
                # Warmup
                case[0]()
                torch.cuda.synchronize()
                implementations['torch-compile'] = (case[0], case[1], {'compiled': True})

        # ============================================================================
        # 2b. torch-bf16-compile (BF16 accumulation)
        # ============================================================================
        if hasattr(torch, 'compile'):
            compiled_bf16 = self.compile_manager.try_compile(torch_bf16_forward)
            if compiled_bf16 is not None:
                case = make_two_input_autograd_case(compiled_bf16)
                # Warmup
                case[0]()
                torch.cuda.synchronize()
                implementations['torch-bf16-compile'] = (case[0], case[1], {'compiled': True})

        # ============================================================================
        # 3. csr-addinto-op (uses shared_flat/shared_weights pattern)
        # ============================================================================
        # The CSR scatter op supports add_into via shared_flat parameter
        # For this benchmark, we simulate it by:
        # - shared_flat = shared_tensor (the pre-existing buffer content)
        # - shared_weights = 1.0 (no scaling, just add)
        def csr_forward(expert_tensor: torch.Tensor, shared_tensor: torch.Tensor) -> torch.Tensor:
            expert_flat = expert_tensor.view(-1, self.config.hidden)
            # Use shared_weights = 1.0 to just add shared_tensor unchanged
            shared_weights = torch.ones(self.config.num_tokens, device=self.device, dtype=torch.float32)
            return csr_scatter_sum(
                expert_flat,
                self.indices_2d,
                self.config.num_tokens,
                self.max_experts,
                self.slot_indices,
                self.slot_offsets,
                self.slot_counts,
                weights_flat=self.weights,
                shared_flat=shared_tensor,
                shared_weights=shared_weights,
            )

        implementations['csr-addinto-op'] = make_two_input_autograd_case(
            csr_forward,
            extras={'triton': True, 'token_parallel': True},
        )

        # ============================================================================
        # 4. csr-addinto-op-compile
        # ============================================================================
        if hasattr(torch, 'compile'):
            csr_compiled = self.compile_manager.try_compile(csr_forward)
            if csr_compiled is not None:
                case = make_two_input_autograd_case(csr_compiled)
                # Warmup
                case[0]()
                torch.cuda.synchronize()
                implementations['csr-addinto-op-compile'] = (
                    case[0], case[1], {'triton': True, 'token_parallel': True, 'compiled': True}
                )

        # ============================================================================
        # 5. csr-optimized-op (CSR scatter with optimized backward + native add_into)
        # ============================================================================
        def csr_optimized_forward(expert_tensor: torch.Tensor, shared_tensor: torch.Tensor) -> torch.Tensor:
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
                add_into_tensor=shared_tensor,  # native add_into support
            )

        implementations['csr-optimized-op'] = make_two_input_autograd_case(
            csr_optimized_forward,
            extras={'triton': True, 'token_parallel': True, 'optimized_bwd': True},
        )

        # ============================================================================
        # 6. csr-optimized-op-compile
        # ============================================================================
        if hasattr(torch, 'compile'):
            csr_opt_compiled = self.compile_manager.try_compile(csr_optimized_forward)
            if csr_opt_compiled is not None:
                case = make_two_input_autograd_case(csr_opt_compiled)
                # Warmup
                case[0]()
                torch.cuda.synchronize()
                implementations['csr-optimized-op-compile'] = (
                    case[0], case[1], {'triton': True, 'token_parallel': True, 'optimized_bwd': True, 'compiled': True}
                )

        return implementations

    def compute_bytes(self) -> float:
        """Compute bytes moved for forward+backward."""
        dtype_size = 2  # BF16

        # Forward: read expert outputs + weights + shared_out, write token outputs
        forward_bytes = (
            self.config.num_experts * self.config.capacity * self.config.hidden  # expert outputs
            + self.config.num_experts * self.config.capacity  # weights
            + self.config.num_tokens * self.config.hidden  # shared_out
            + self.config.num_tokens * self.config.hidden  # output
        ) * dtype_size

        # Backward: read grad_output, write grad_expert + grad_shared + grad_weights
        backward_bytes = (
            self.config.num_tokens * self.config.hidden  # grad_output
            + self.config.num_experts * self.config.capacity * self.config.hidden  # grad_expert
            + self.config.num_tokens * self.config.hidden  # grad_shared
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
            'shared_template': {
                'min': float(self.shared_template.min()),
                'max': float(self.shared_template.max()),
                'mean': float(self.shared_template.mean()),
                'std': float(self.shared_template.std()),
            },
            'loss_grad': {
                'min': float(self.loss_weights.min()),
                'max': float(self.loss_weights.max()),
                'mean': float(self.loss_weights.mean()),
                'std': float(self.loss_weights.std()),
            },
        }
