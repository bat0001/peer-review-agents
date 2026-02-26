"""Scatter benchmark with all implementations (forward only, with weights)."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import torch

from benchmark.permutation.base import BaseKernelBenchmark
from benchmark.permutation.common import BenchmarkResult, format_results, format_stats
from benchmark.permutation.core import BenchmarkConfig, add_standard_args, args_to_config, setup_environment
from src import kernels as balanced_kernels
from src.kernels.sequential import _sequential_add


def build_inverse_indices(
    indices: torch.Tensor,
    num_tokens: int,
    max_experts: int,
) -> torch.Tensor:
    """Convert flat expert→token indices to token→expert positions mapping.

    Args:
        indices: (num_experts * capacity,) flat indices mapping expert buffer positions to token IDs
        num_tokens: Total number of tokens
        max_experts: Maximum number of expert contributions per token (G * E)

    Returns:
        inverse_indices: (num_tokens, max_experts) int32 tensor
            For each token, stores linear buffer positions of contributing experts.
            Padded with -1 for unused slots.
    """
    # Count contributions per token
    counts = torch.zeros(num_tokens, dtype=torch.int32, device=indices.device)
    indices_int32 = indices.to(torch.int32)
    counts.scatter_add_(0, indices_int32, torch.ones_like(indices_int32))

    # Verify MAX_EXPERTS is sufficient
    actual_max = counts.max().item()
    if actual_max > max_experts:
        raise ValueError(
            f"MAX_EXPERTS={max_experts} is insufficient. "
            f"Found token with {actual_max} expert contributions. "
            f"Need MAX_EXPERTS >= {actual_max}"
        )

    # Build inverse mapping
    inverse_indices = torch.full(
        (num_tokens, max_experts), -1, dtype=torch.int32, device=indices.device
    )
    position_counters = torch.zeros(num_tokens, dtype=torch.int32, device=indices.device)

    for linear_pos in range(len(indices)):
        token_id = indices_int32[linear_pos].item()
        slot = position_counters[token_id].item()
        inverse_indices[token_id, slot] = linear_pos
        position_counters[token_id] += 1

    return inverse_indices


class ScatterForwardBenchmark(BaseKernelBenchmark):
    """Benchmark for scatter kernel (forward only, with weights).

    Consolidates all scatter implementations:
    - index_add (reference)
    - triton-atomic
    - sequential (no atomics)
    - csr-scatter (token-parallel)
    - buffer-reduce (dense approach)

    All implementations validate against index_add reference.
    """

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__(config)
        self.expert_out: Optional[torch.Tensor] = None
        self.expert_out_flat: Optional[torch.Tensor] = None
        self.weights_flat_fp32: Optional[torch.Tensor] = None
        self.max_experts: int = config.granularity * config.expansion  # G * E

        # For sequential kernel
        self.inverse_indices: Optional[torch.Tensor] = None

        # For CSR kernel
        self.indices_2d: Optional[torch.Tensor] = None
        self.slot_indices: Optional[torch.Tensor] = None
        self.slot_offsets: Optional[torch.Tensor] = None
        self.slot_counts: Optional[torch.Tensor] = None

        # For buffer-reduce
        self.expert_ids: Optional[torch.Tensor] = None

    def setup_data(self) -> None:
        """Setup scatter input tensors."""
        self.setup_common_data()
        self.expert_out = torch.randn(
            (self.config.num_experts, self.config.capacity, self.config.hidden),
            dtype=torch.bfloat16,
            device=self.device,
        )
        self.expert_out_flat = self.expert_out.view(-1, self.config.hidden)
        self.weights_flat_fp32 = self.weights.view(-1, 1)

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

        # Build expert IDs for buffer-reduce
        self.expert_ids = torch.arange(
            self.config.num_experts, device=self.device, dtype=torch.int64
        ).repeat_interleave(self.config.capacity)

    def create_implementations(self) -> Dict[str, Tuple[Callable[[], None], Callable, Dict[str, float | bool]]]:
        """Create all scatter implementations (all with weights, all test raw and compiled)."""
        implementations = {}

        # ============================================================================
        # 1. torch (REFERENCE - FP32 accumulation, matches Triton kernel semantics)
        # ============================================================================
        def index_add_kernel() -> torch.Tensor:
            weighted = self.expert_out_flat.float() * self.weights_flat_fp32
            out = torch.zeros(
                (self.config.num_tokens, self.config.hidden),
                dtype=torch.float32,
                device=self.device,
            )
            out.index_add_(0, self.indices, weighted)
            return out.to(torch.bfloat16)

        def index_add_runner() -> None:
            index_add_kernel()

        implementations['torch'] = (index_add_runner, index_add_kernel, {'weight_fused': True})

        # ============================================================================
        # 1b. torch-bf16 (native BF16 accumulation - shows PyTorch default behavior)
        # ============================================================================
        def index_add_bf16_kernel() -> torch.Tensor:
            weighted = torch.mul(self.expert_out_flat, self.weights_flat_fp32)
            out = torch.zeros(
                (self.config.num_tokens, self.config.hidden),
                dtype=torch.bfloat16,
                device=self.device,
            )
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
        # 3. triton-atomic
        # ============================================================================
        def triton_atomic_impl() -> torch.Tensor:
            return balanced_kernels.scatter_atomic(
                self.expert_out,
                self.indices,
                num_experts=self.config.num_experts,
                capacity=self.config.capacity,
                num_tokens=self.config.num_tokens,
                weights=self.weights,
            )

        def triton_atomic_runner() -> None:
            triton_atomic_impl()

        implementations['triton-atomic'] = (
            triton_atomic_runner, triton_atomic_impl, {'weight_fused': True, 'triton': True}
        )

        # ============================================================================
        # 4. triton-atomic-compile
        # ============================================================================
        triton_compiled = self.compile_manager.try_compile(triton_atomic_impl)
        if triton_compiled is not None:
            def triton_compiled_runner() -> None:
                triton_compiled()

            implementations['triton-atomic-compile'] = (
                triton_compiled_runner, triton_compiled,
                {'weight_fused': True, 'triton': True, 'compiled': True}
            )

        # ============================================================================
        # 5. sequential (no atomics)
        # ============================================================================
        def sequential_impl() -> torch.Tensor:
            out = torch.zeros(
                (self.config.num_tokens, self.config.hidden),
                dtype=torch.bfloat16,
                device=self.device,
            )
            _sequential_add[self.config.num_tokens,](
                self.expert_out_flat,
                out,
                self.inverse_indices,
                self.weights,
                MAX_EXPERTS=self.max_experts,
                NUM_COLUMNS=self.config.hidden,
                SCALE=True,
                ADD_INTO=False,
            )
            return out

        def sequential_runner() -> None:
            sequential_impl()

        implementations['sequential'] = (
            sequential_runner, sequential_impl, {'weight_fused': True}
        )

        # ============================================================================
        # 6. sequential-compile
        # ============================================================================
        seq_compiled = self.compile_manager.try_compile(sequential_impl)
        if seq_compiled is not None:
            def seq_compiled_runner() -> None:
                seq_compiled()

            implementations['sequential-compile'] = (
                seq_compiled_runner, seq_compiled, {'weight_fused': True, 'compiled': True}
            )

        # ============================================================================
        # 7. csr-scatter (NEW - token-parallel)
        # ============================================================================
        from src.kernels.csr import _csr_scatter_sum

        def csr_impl() -> torch.Tensor:
            out = torch.zeros(
                (self.config.num_tokens, self.config.hidden),
                dtype=torch.bfloat16,
                device=self.device,
            )
            # Launch token-parallel kernel
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
                ACCUMULATE=0,
                SHARED_EXPERT_WEIGHTS=0,
                shared_expert_weights=out,  # dummy pointer
            )
            return out

        def csr_runner() -> None:
            csr_impl()

        implementations['csr-scatter'] = (
            csr_runner, csr_impl, {'weight_fused': True, 'triton': True, 'token_parallel': True}
        )

        # ============================================================================
        # 8. csr-scatter-compile
        # ============================================================================
        csr_compiled = self.compile_manager.try_compile(csr_impl)
        if csr_compiled is not None:
            def csr_compiled_runner() -> None:
                csr_compiled()

            implementations['csr-scatter-compile'] = (
                csr_compiled_runner, csr_compiled,
                {'weight_fused': True, 'triton': True, 'token_parallel': True, 'compiled': True}
            )

        # ============================================================================
        # 9. buffer-reduce (dense approach, for comparison)
        # ============================================================================
        def buffer_kernel() -> torch.Tensor:
            weighted = torch.mul(self.expert_out_flat, self.weights_flat_fp32)
            token_buffer = torch.zeros(
                (self.config.num_tokens, self.config.num_experts, self.config.hidden),
                dtype=torch.bfloat16,
                device=self.device,
            )
            token_buffer.index_put_(
                (self.indices, self.expert_ids),
                weighted.to(token_buffer.dtype),
            )
            return token_buffer.sum(dim=1)

        buffer_numel = self.config.num_tokens * self.config.num_experts * self.config.hidden
        buffer_gb = buffer_numel * self.expert_out.element_size() / 1e9

        def buffer_runner() -> None:
            buffer_kernel()

        implementations['buffer-reduce'] = (
            buffer_runner, buffer_kernel, {'weight_fused': True, 'buffer_gb': buffer_gb}
        )

        # ============================================================================
        # 10. buffer-reduce-compile
        # ============================================================================
        buffer_compiled = self.compile_manager.try_compile(buffer_kernel)
        if buffer_compiled is not None:
            def buffer_compiled_runner() -> None:
                buffer_compiled()

            implementations['buffer-reduce-compile'] = (
                buffer_compiled_runner, buffer_compiled,
                {'weight_fused': True, 'buffer_gb': buffer_gb, 'compiled': True}
            )

        return implementations

    def compute_bytes(self) -> float:
        """Compute bytes moved for scatter operation."""
        # Read expert outputs + weights, write token outputs
        return 2 * self.config.num_experts * self.config.capacity * self.config.hidden * self.expert_out.element_size()

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics."""
        return {
            'weights': {
                'min': float(self.weights.min()),
                'max': float(self.weights.max()),
                'mean': float(self.weights.mean()),
                'std': float(self.weights.std()),
            }
        }
