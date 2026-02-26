"""Scatter backends for aggregating expert outputs to tokens.

Two backends available:
- IndexAddScatter: Uses PyTorch index_add_ (simple, no custom kernels)
- CSRScatter: Uses CSR kernel (token-parallel, fused weighted scatter)

Both backends apply weights during scatter (fused operation) and support
shared expert fusion via shared_flat/shared_weights parameters.

Usage:
    scatter = get_scatter('index_add')  # or 'csr'

    # GEC (routed only)
    output = scatter(h_flat, indices_flat, n_tokens, weights_flat)

    # GEC_shared (with shared expert fusion)
    output = scatter(h_flat, indices_flat, n_tokens, weights_flat,
                     shared_flat=shared_output, shared_weights=1/normalizer)
"""

from typing import Optional

import torch
from torch import Tensor

from src import kernels
from .csr import csr_scatter_sum
from .csr_optimized import csr_scatter_sum_optimized


class IndexAddScatter:
    """Scatter using PyTorch index_add_ with fused weight application.

    When weights are fp32, accumulation happens in fp32 for numerical stability,
    then output is cast back to h_flat's dtype (typically bf16).
    """

    def __call__(
        self,
        h_flat: Tensor,
        indices_flat: Tensor,
        n_tokens: int,
        weights_flat: Tensor,
        shared_flat: Optional[Tensor] = None,
        shared_weights: Optional[Tensor] = None,
    ) -> Tensor:
        """Scatter expert outputs to tokens with fused weighting.

        Args:
            h_flat: Expert outputs (total_active, H) UNWEIGHTED
            indices_flat: Token indices (total_active,) - flat, 1D
            n_tokens: Total number of tokens (N)
            weights_flat: Weights to apply (total_active,) - fp32 for numerical stability
            shared_flat: Optional shared expert output (N, H) UNWEIGHTED
            shared_weights: Optional shared expert weights (N,) = 1/normalizer

        Returns:
            Token outputs (N, H) in h_flat's dtype
        """
        H = h_flat.shape[1]
        target_dtype = h_flat.dtype

        # Determine accumulation dtype (use fp32 if weights are fp32)
        accum_dtype = weights_flat.dtype if weights_flat.dtype == torch.float32 else h_flat.dtype

        # Apply weights to routed expert outputs (promotes to accum_dtype if weights are fp32)
        h_weighted = h_flat.to(accum_dtype) * weights_flat.unsqueeze(-1)

        # Initialize output with weighted shared expert (if provided)
        if shared_flat is not None and shared_weights is not None:
            # Align shared weights to accumulation dtype to avoid mixed-dtype index_add_
            shared_weights = shared_weights.to(accum_dtype)
            output = shared_flat.to(accum_dtype) * shared_weights.unsqueeze(-1)
        else:
            output = torch.zeros(n_tokens, H, device=h_flat.device, dtype=accum_dtype)

        output.index_add_(0, indices_flat, h_weighted)

        # Cast back to original dtype
        return output.to(target_dtype)


class IndexAddScatterFP32:
    """Scatter using PyTorch index_add_ in FP32 (accumulates in float32)."""

    def __call__(
        self,
        h_flat: Tensor,
        indices_flat: Tensor,
        n_tokens: int,
        weights_flat: Tensor,
        shared_flat: Optional[Tensor] = None,
        shared_weights: Optional[Tensor] = None,
    ) -> Tensor:
        """Scatter expert outputs to tokens with fused weighting in FP32.

        Args:
            h_flat: Expert outputs (total_active, H) UNWEIGHTED
            indices_flat: Token indices (total_active,) - flat, 1D
            n_tokens: Total number of tokens (N)
            weights_flat: Weights to apply (total_active,)
            shared_flat: Optional shared expert output (N, H) UNWEIGHTED
            shared_weights: Optional shared expert weights (N,) = 1/normalizer

        Returns:
            Token outputs (N, H) in original dtype
        """
        H = h_flat.shape[1]
        target_dtype = h_flat.dtype

        # Apply weights to routed expert outputs in FP32
        h_weighted = h_flat.float() * weights_flat.float().unsqueeze(-1)

        # Initialize output with weighted shared expert (if provided) in FP32
        if shared_flat is not None and shared_weights is not None:
            output = shared_flat.float() * shared_weights.float().unsqueeze(-1)
        else:
            output = torch.zeros(n_tokens, H, device=h_flat.device, dtype=torch.float32)

        output.index_add_(0, indices_flat, h_weighted)

        # Cast back to original dtype
        return output.to(target_dtype)


class CSRScatter:
    """Scatter using CSR kernel with fully fused weighted scatter."""

    def __init__(self, max_fanout: int):
        """Initialize CSR scatter backend.

        Args:
            max_fanout: Maximum number of experts per token (compile-time bound)
        """
        self.max_fanout = max_fanout

    def __call__(
        self,
        h_flat: Tensor,
        indices_flat: Tensor,
        n_tokens: int,
        weights_flat: Tensor,
        shared_flat: Optional[Tensor] = None,
        shared_weights: Optional[Tensor] = None,
    ) -> Tensor:
        """Scatter expert outputs to tokens using CSR kernel with fused weighting.

        The kernel applies routed weights and shared weights in a single pass.

        Args:
            h_flat: Expert outputs (total_active, H) UNWEIGHTED
            indices_flat: Token indices (total_active,) - flat, 1D
            n_tokens: Total number of tokens (N)
            weights_flat: Weights to apply to routed experts (total_active,)
            shared_flat: Optional shared expert output (N, H) UNWEIGHTED
            shared_weights: Optional shared expert weights (N,) = 1/normalizer

        Returns:
            Token outputs (N, H)
        """
        # Build CSR metadata from flat indices
        slot_indices, slot_offsets, slot_counts = kernels.build_slot_indices_flat(
            indices_flat, num_tokens=n_tokens, max_experts=self.max_fanout
        )

        return csr_scatter_sum(
            h_flat,
            indices_flat,
            num_tokens=n_tokens,
            max_experts=self.max_fanout,
            slot_indices=slot_indices,
            slot_offsets=slot_offsets,
            slot_counts=slot_counts,
            weights_flat=weights_flat,
            shared_flat=shared_flat,
            shared_weights=shared_weights,
        )


class CSRScatterOptimized:
    """Scatter using CSR kernel with optimized backward pass.

    Same forward as CSRScatter, but backward uses optimized kernel with
    column-major loop ordering for better L1 cache utilization.
    """

    def __init__(self, max_fanout: int):
        self.max_fanout = max_fanout

    def __call__(
        self,
        h_flat: Tensor,
        indices_flat: Tensor,
        n_tokens: int,
        weights_flat: Tensor,
        shared_flat: Optional[Tensor] = None,
        shared_weights: Optional[Tensor] = None,
    ) -> Tensor:
        # Build CSR metadata from flat indices
        slot_indices, slot_offsets, slot_counts = kernels.build_slot_indices_flat(
            indices_flat, num_tokens=n_tokens, max_experts=self.max_fanout
        )

        return csr_scatter_sum_optimized(
            h_flat,
            indices_flat,
            n_tokens,
            self.max_fanout,
            slot_indices,
            slot_offsets,
            slot_counts,
            weights_flat,
            shared_flat,
            shared_weights,
        )


def get_scatter(backend: str, max_fanout: int = None):
    """Factory function to get scatter backend.

    Args:
        backend: 'index_add', 'index_add_fp32', 'csr', or 'csr_optimized'
        max_fanout: Maximum experts per token (required for CSR backends)

    Returns:
        Scatter backend instance
    """
    if backend == 'csr':
        assert max_fanout is not None, "CSR scatter requires max_fanout"
        return CSRScatter(max_fanout)
    elif backend == 'csr_optimized':
        assert max_fanout is not None, "CSR scatter requires max_fanout"
        return CSRScatterOptimized(max_fanout)
    elif backend == 'index_add_fp32':
        return IndexAddScatterFP32()
    else:
        return IndexAddScatter()


__all__ = ['IndexAddScatter', 'IndexAddScatterFP32', 'CSRScatter', 'CSRScatterOptimized', 'get_scatter']
