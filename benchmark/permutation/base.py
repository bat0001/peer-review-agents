"""Base classes for permutation benchmarks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Tuple

import torch

from benchmark.shared.compile import TorchCompileManager
from benchmark.shared.config import BenchmarkConfig, get_tolerance
from benchmark.shared.results import BenchmarkResult, measure


class BaseBenchmark(ABC):
    """Base class for all permutation benchmarks."""

    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config
        self.config.validate()
        self.device = config.device
        self.tolerance = get_tolerance()  # BF16 mixed precision tolerance
        self.compile_manager = TorchCompileManager()

    @abstractmethod
    def setup_data(self) -> None:
        """Setup benchmark data tensors."""
        ...

    @abstractmethod
    def create_implementations(self) -> Dict[str, Tuple[Callable[[], None], Callable, Dict[str, float | bool]]]:
        """
        Create benchmark implementations.

        Returns:
            Dict mapping name -> (runner_fn, output_fn, extras_dict)
        """
        ...

    @abstractmethod
    def compute_bytes(self) -> float:
        """Compute total bytes moved for bandwidth calculation."""
        ...

    def run_single_case(
        self, weight_grads: Optional[Dict[str, torch.Tensor]] = None
    ) -> Tuple[List[BenchmarkResult], Dict[str, Dict[str, float]]]:
        """Run benchmark and return results."""
        self.setup_data()
        implementations = self.create_implementations()

        reference_name = 'torch'
        if reference_name not in implementations:
            raise ValueError(f'Reference implementation "{reference_name}" not found')

        reference = implementations[reference_name][1]().detach().to(torch.float32)
        weights_reference = weight_grads.get(reference_name) if weight_grads else None
        bytes_moved = self.compute_bytes()

        results: List[BenchmarkResult] = []
        for name, (runner, output_fn, extras) in implementations.items():
            torch.cuda.reset_peak_memory_stats(self.device)
            time_ms = measure(runner, repeats=self.config.repeats, warmup=self.config.warmup)
            peak_bytes = torch.cuda.max_memory_allocated(self.device)

            out = output_fn().detach().to(torch.float32)
            extras_copy: Dict[str, float | bool] = dict(extras)

            if name == reference_name:
                matches = True
                diff = None
            else:
                diff_tensor = (out - reference).abs()
                diff = float(diff_tensor.max()) if diff_tensor.numel() > 0 else 0.0
                mean_diff = float(diff_tensor.mean()) if diff_tensor.numel() > 0 else 0.0
                matches = diff <= self.tolerance
                extras_copy['mean_diff'] = mean_diff

                # Check weight gradients if provided
                if weight_grads and weights_reference is not None:
                    candidate = weight_grads.get(name)
                    if candidate is None:
                        matches = False
                        extras_copy['grad_w_match'] = False
                    else:
                        grad_w_diff = (candidate.to(torch.float32) - weights_reference.to(torch.float32)).abs()
                        max_grad_w_diff = float(grad_w_diff.max()) if grad_w_diff.numel() > 0 else 0.0
                        extras_copy['grad_w_max'] = max_grad_w_diff
                        grad_match = max_grad_w_diff <= self.tolerance
                        extras_copy['grad_w_match'] = grad_match
                        matches = matches and grad_match

            results.append(
                BenchmarkResult(
                    name=name,
                    time_ms=time_ms,
                    gbps=bytes_moved / time_ms / 1e6,
                    bytes_moved=bytes_moved,
                    matches=matches,
                    max_abs_diff=diff,
                    peak_mem_gb=peak_bytes / 1e9,
                    extras=extras_copy,
                )
            )

        stats = self.get_stats()
        compile_stats = self.compile_manager.get_stats()
        if compile_stats.get('available'):
            stats['compile'] = compile_stats

        return results, stats

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get additional statistics for this benchmark. Override in subclasses."""
        return {}

    def add_torch_compile(
        self,
        implementations: Dict,
        compilable_fn: Callable,
        *args,
        extras: Optional[Dict[str, float | bool]] = None,
        weight_grads_dict: Optional[Dict[str, torch.Tensor]] = None,
        weight_grads_key: str = 'torch-compile',
    ) -> None:
        """
        Add torch-compile version to implementations.

        Args:
            implementations: Dict to add to
            compilable_fn: Function to compile
            *args: Args to pass to compiled function
            extras: Extra metadata
            weight_grads_dict: Optional dict to store weight gradients
            weight_grads_key: Key to use in weight_grads_dict (default: 'torch-compile')
        """
        compiled = self.compile_manager.try_compile(compilable_fn)
        if compiled is not None:

            def compiled_runner() -> None:
                result = compiled(*args)
                # Store weight grad if tracking
                if weight_grads_dict is not None:
                    if isinstance(result, tuple) and len(result) == 2:
                        weight_grads_dict[weight_grads_key] = result[1]

            def compiled_output():
                result = compiled(*args)
                # Store weight grad if tracking
                if weight_grads_dict is not None and isinstance(result, tuple) and len(result) == 2:
                    weight_grads_dict[weight_grads_key] = result[1]
                    return result[0]
                return result

            compiled_extras = {**(extras or {}), 'compiled': True}
            implementations['torch-compile'] = (compiled_runner, compiled_output, compiled_extras)


class BaseKernelBenchmark(BaseBenchmark):
    """Base class for kernel-only benchmarks (gather, scatter)."""

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__(config)
        self.indices: Optional[torch.Tensor] = None
        self.weights: Optional[torch.Tensor] = None

    def setup_common_data(self) -> None:
        """Setup indices and weights common to kernel benchmarks."""
        scores = torch.randn(
            (self.config.num_experts, self.config.num_tokens),
            dtype=torch.float32,
            device=self.device,
        )
        # Expert-major topk: each expert selects top-k tokens
        self.indices = torch.topk(scores, k=self.config.capacity, dim=1, largest=True, sorted=True).indices.reshape(-1)
        self.weights = torch.sigmoid(
            torch.randn(self.indices.shape[0], dtype=torch.float32, device=self.device)
        )


class BaseAutogradBenchmark(BaseBenchmark):
    """Base class for autograd benchmarks (gather-op, scatter-op)."""

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__(config)
        self.indices: Optional[torch.Tensor] = None

    def setup_indices(self) -> None:
        """Setup routing indices."""
        scores = torch.randn(
            (self.config.num_experts, self.config.num_tokens),
            dtype=torch.float32,
            device=self.device,
        )
        # Expert-major topk: each expert selects top-k tokens
        self.indices = torch.topk(scores, k=self.config.capacity, dim=1, largest=True, sorted=True).indices.reshape(-1)

    def make_autograd_case(
        self,
        forward_fn: Callable[[torch.Tensor], torch.Tensor],
        loss_weights: torch.Tensor,
        input_template: torch.Tensor,
        extras: Optional[Dict[str, float | bool]] = None,
    ) -> Tuple[Callable[[], None], Callable[[], Tuple[torch.Tensor, torch.Tensor]], Dict[str, float | bool]]:
        """
        Create autograd benchmark case (forward + backward).

        Args:
            forward_fn: Function taking input tensor, returning output
            loss_weights: Weights for computing loss from output
            input_template: Template tensor for creating work tensor
            extras: Extra metadata

        Returns:
            (runner_fn, outputs_fn, extras_dict)
        """
        work_tensor = input_template.clone().detach().requires_grad_(True)
        loss_weights = loss_weights.detach()

        def runner() -> None:
            if work_tensor.grad is not None:
                work_tensor.grad.zero_()
            out = forward_fn(work_tensor)
            loss = torch.sum(out * loss_weights)
            loss.backward()

        def outputs() -> Tuple[torch.Tensor, torch.Tensor]:
            if work_tensor.grad is not None:
                work_tensor.grad.zero_()
            out = forward_fn(work_tensor)
            loss = torch.sum(out * loss_weights)
            loss.backward()
            forward_fp32 = out.detach().to(torch.float32)
            grad_fp32 = work_tensor.grad.detach().clone().to(torch.float32)
            if work_tensor.grad is not None:
                work_tensor.grad.zero_()
            return forward_fp32, grad_fp32

        return runner, outputs, extras or {}

    def run_autograd_case(self) -> Tuple[List[BenchmarkResult], Dict[str, Dict[str, float]]]:
        """
        Run autograd benchmark and return results.

        Different from run_single_case because outputs are (forward, grad) tuples.
        """
        self.setup_data()
        implementations = self.create_implementations()

        reference_name = 'torch'
        if reference_name not in implementations:
            raise ValueError(f'Reference implementation "{reference_name}" not found')

        reference_forward, reference_grad = implementations[reference_name][1]()
        bytes_moved = self.compute_bytes()

        results: List[BenchmarkResult] = []
        for name, (runner, output_fn, extras) in implementations.items():
            torch.cuda.reset_peak_memory_stats(self.device)
            time_ms = measure(runner, repeats=self.config.repeats, warmup=self.config.warmup)
            peak_bytes = torch.cuda.max_memory_allocated(self.device)

            forward_out, grad_out = output_fn()

            if name == reference_name:
                matches = True
                max_diff = None
                extras_out = {'baseline': True, **extras}
            else:
                fwd_diff_tensor = (forward_out - reference_forward).abs()
                grad_diff_tensor = (grad_out - reference_grad).abs()
                fwd_diff = float(fwd_diff_tensor.max()) if fwd_diff_tensor.numel() > 0 else 0.0
                grad_diff = float(grad_diff_tensor.max()) if grad_diff_tensor.numel() > 0 else 0.0
                fwd_mean = float(fwd_diff_tensor.mean()) if fwd_diff_tensor.numel() > 0 else 0.0
                grad_mean = float(grad_diff_tensor.mean()) if grad_diff_tensor.numel() > 0 else 0.0
                matches = fwd_diff <= self.tolerance and grad_diff <= self.tolerance
                max_diff = max(fwd_diff, grad_diff)
                extras_out = {
                    **extras,
                    'fwd_diff': fwd_diff,
                    'grad_diff': grad_diff,
                    'fwd_mean': fwd_mean,
                    'grad_mean': grad_mean,
                }

            results.append(
                BenchmarkResult(
                    name=name,
                    time_ms=time_ms,
                    gbps=bytes_moved / time_ms / 1e6,
                    bytes_moved=bytes_moved,
                    matches=matches,
                    max_abs_diff=max_diff,
                    peak_mem_gb=peak_bytes / 1e9,
                    extras=extras_out,
                )
            )

        stats = self.get_stats()
        compile_stats = self.compile_manager.get_stats()
        if compile_stats.get('available'):
            stats['compile'] = compile_stats

        return results, stats


__all__ = ['BaseBenchmark', 'BaseKernelBenchmark', 'BaseAutogradBenchmark']
