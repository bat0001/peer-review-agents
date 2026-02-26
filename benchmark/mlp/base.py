"""Base classes for MLP benchmarks."""

from __future__ import annotations

import gc
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Tuple

import torch
import torch.nn as nn

from benchmark.shared.compile import TorchCompileManager
from benchmark.shared.config import BenchmarkConfig, get_tolerance
from benchmark.shared.results import BenchmarkResult, measure


class MLPBenchmark(ABC):
    """Base class for MLP benchmarks."""

    def __init__(self, config: BenchmarkConfig, model_config: Optional[Dict] = None) -> None:
        """
        Initialize MLP benchmark.

        Args:
            config: Benchmark configuration (tokens, hidden, experts, etc.)
            model_config: Optional model-specific config overrides
        """
        self.config = config
        self.config.validate()
        self.device = config.device
        self.tolerance = get_tolerance()  # BF16 mixed precision tolerance
        self.compile_manager = TorchCompileManager()

        # Model configuration derived from benchmark config
        self.model_config = model_config or self._create_model_config()

    def _create_model_config(self) -> Dict:
        """Create model configuration from benchmark config.

        Override this in subclasses to provide model-specific configuration.
        """
        G = self.config.granularity
        E = self.config.expansion
        expert_dim = (4 * self.config.hidden) // G

        return {
            'n_embd': self.config.hidden,
            'n_experts': self.config.num_experts,
            'expert_dim': expert_dim,
            'granularity': G,
            'expansion': E,
        }

    @abstractmethod
    def setup_data(self) -> None:
        """Setup benchmark data tensors and models."""
        ...

    @abstractmethod
    def create_implementations(self) -> Dict[str, Tuple[Callable[[], None], Callable, Dict[str, float | bool]]]:
        """
        Create benchmark implementations.

        Returns:
            Dict mapping name -> (runner_fn, output_fn, extras_dict)
            - runner_fn: Callable that runs the operation
            - output_fn: Callable that returns output tensor
            - extras_dict: Additional metrics (flops, params, etc.)
        """
        ...

    @abstractmethod
    def compute_bytes(self) -> float:
        """Compute total bytes moved for bandwidth calculation."""
        ...

    def get_implementation_groups(self) -> Dict[str, List[str]]:
        """
        Define reference groups for validation.

        Each group has a reference implementation and variants that should
        produce functionally equivalent results.

        Returns:
            Dict mapping reference_name -> list of implementation names

        Example:
            {
                'dense': ['dense'],
                'gec': ['gec', 'gec-triton-balanced', 'gec-triton-atomic']
            }

        Note: The reference name (dict key) must be in its own list.
        """
        return {}  # Default: no grouping (backwards compatible)

    def _collect_group_stats(
        self, outputs: Dict[str, torch.Tensor], groups: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, float]]:
        """Collect validation statistics per group."""
        stats: Dict[str, Dict[str, float]] = {}

        for ref_name, group_members in groups.items():
            if ref_name not in outputs:
                continue

            ref_output = outputs[ref_name]
            group_stats = {
                'ref_mean': float(ref_output.mean()),
                'ref_std': float(ref_output.std()),
                'ref_min': float(ref_output.min()),
                'ref_max': float(ref_output.max()),
            }

            # Per-member comparison stats
            for member in group_members:
                if member == ref_name or member not in outputs:
                    continue

                diff = (outputs[member] - ref_output).abs()
                group_stats[f'{member}_max_diff'] = float(diff.max())
                group_stats[f'{member}_mean_diff'] = float(diff.mean())
                group_stats[f'{member}_rel_error'] = float(diff.mean() / (ref_output.abs().mean() + 1e-8))

            stats[f'group_{ref_name}'] = group_stats

        return stats

    def run_single_case(
        self, weight_grads: Optional[Dict[str, torch.Tensor]] = None
    ) -> Tuple[List[BenchmarkResult], Dict[str, Dict[str, float]]]:
        """Run benchmark with two-stage validation."""
        # ═══════════════════════════════════════════════════════
        # SETUP
        # ═══════════════════════════════════════════════════════
        self.setup_data()
        implementations = self.create_implementations()
        groups = self.get_implementation_groups()
        bytes_moved = self.compute_bytes()

        # If no groups defined, create default single-reference group
        if not groups:
            first_impl = next(iter(implementations.keys()))
            groups = {first_impl: list(implementations.keys())}

        # ═══════════════════════════════════════════════════════
        # STAGE 1: CLEAN PERFORMANCE MEASUREMENT
        # ═══════════════════════════════════════════════════════
        results: List[BenchmarkResult] = []

        for name, (runner, output_fn, extras) in implementations.items():
            # Clear any benchmark-held outputs from previous iteration
            if hasattr(self, 'outputs'):
                self.outputs.clear()

            # Clean CUDA state for accurate measurement
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.synchronize(self.device)
            torch.cuda.reset_peak_memory_stats(self.device)

            # Measure performance without storing outputs
            time_ms = measure(runner, repeats=self.config.repeats, warmup=self.config.warmup)
            peak_bytes = torch.cuda.max_memory_allocated(self.device)

            # Store result (validation fields are None for now)
            results.append(
                BenchmarkResult(
                    name=name,
                    time_ms=time_ms,
                    gbps=bytes_moved / time_ms / 1e6,
                    bytes_moved=bytes_moved,
                    matches=None,  # Will be set in stage 2
                    max_abs_diff=None,  # Will be set in stage 2
                    peak_mem_gb=peak_bytes / 1e9,
                    extras=dict(extras),
                )
            )

        # ═══════════════════════════════════════════════════════
        # STAGE 2: CORRECTNESS VALIDATION
        # ═══════════════════════════════════════════════════════
        torch.cuda.empty_cache()
        torch.cuda.synchronize(self.device)

        # Run each implementation ONCE to collect outputs
        outputs: Dict[str, torch.Tensor] = {}
        for name, (runner, output_fn, extras) in implementations.items():
            runner()  # Execute once
            outputs[name] = output_fn().detach().to(torch.float32)

        # Validate within reference groups (skip if reference doesn't exist)
        for reference_name, group_members in groups.items():
            if reference_name not in outputs:
                continue  # Skip groups where reference wasn't run

            reference_output = outputs[reference_name]

            # Compare each group member against the reference
            for result in results:
                if result.name not in group_members:
                    continue  # Not in this group

                if result.name == reference_name:
                    # Reference implementation matches itself
                    result.matches = True
                    result.max_abs_diff = None
                else:
                    # Compare variant against reference
                    candidate = outputs[result.name]
                    diff_tensor = (candidate - reference_output).abs()
                    max_diff = float(diff_tensor.max()) if diff_tensor.numel() > 0 else 0.0
                    mean_diff = float(diff_tensor.mean()) if diff_tensor.numel() > 0 else 0.0

                    result.max_abs_diff = max_diff
                    result.mean_abs_diff = mean_diff
                    result.matches = max_diff <= self.tolerance

                    # Add numerical diagnostics when there's a mismatch
                    if not result.matches:
                        # Value ranges
                        result.diagnostics['ref_min'] = float(reference_output.min())
                        result.diagnostics['ref_max'] = float(reference_output.max())
                        result.diagnostics['test_min'] = float(candidate.min())
                        result.diagnostics['test_max'] = float(candidate.max())

                        # Sample mismatches: find positions with largest errors
                        if diff_tensor.numel() > 0:
                            flat_diff = diff_tensor.flatten()
                            flat_ref = reference_output.flatten()
                            flat_test = candidate.flatten()

                            # Get top 3 mismatches
                            top_k = min(3, flat_diff.numel())
                            _, top_indices = torch.topk(flat_diff, top_k)

                            samples = []
                            for idx in top_indices:
                                idx_val = int(idx)
                                ref_val = float(flat_ref[idx_val])
                                test_val = float(flat_test[idx_val])
                                # Convert flat index to multi-dimensional index
                                multi_idx = []
                                remaining = idx_val
                                for dim in reversed(candidate.shape):
                                    multi_idx.insert(0, remaining % dim)
                                    remaining //= dim
                                samples.append((tuple(multi_idx), ref_val, test_val))

                            result.diagnostics['sample_diffs'] = samples

        # Collect statistics
        stats = self._collect_group_stats(outputs, groups)

        return results, stats


class MLPAutogradBenchmark(MLPBenchmark):
    """Base class for autograd benchmarks (forward + backward)."""

    def __init__(self, config: BenchmarkConfig, model_config: Optional[Dict] = None) -> None:
        super().__init__(config, model_config)
        self.mode = 'forward-backward'

    @abstractmethod
    def create_autograd_implementations(self) -> Dict[str, Tuple[nn.Module, Dict[str, float | bool]]]:
        """
        Create autograd implementations.

        Returns:
            Dict mapping name -> (module, extras_dict)
        """
        ...

    def run_autograd_case(self) -> Tuple[List[BenchmarkResult], Dict[str, Dict[str, float]]]:
        """Run autograd benchmark (forward + backward) with two-stage validation."""
        # ═══════════════════════════════════════════════════════
        # SETUP
        # ═══════════════════════════════════════════════════════
        self.setup_data()
        implementations = self.create_autograd_implementations()
        groups = self.get_implementation_groups()
        bytes_moved = self.compute_bytes()

        # If no groups defined, create default single-reference group
        if not groups:
            first_impl = next(iter(implementations.keys()))
            groups = {first_impl: list(implementations.keys())}

        # ═══════════════════════════════════════════════════════
        # STAGE 1: CLEAN PERFORMANCE MEASUREMENT
        # ═══════════════════════════════════════════════════════
        results: List[BenchmarkResult] = []

        for name, (module, extras) in implementations.items():
            module = module.to(self.device)

            def runner():
                input_copy = self.input_tensor.clone().requires_grad_(True)
                with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
                    out = module(input_copy)
                    if isinstance(out, tuple):
                        out = out[0]
                    loss = out.sum()
                loss.backward()

            # Clear any benchmark-held outputs from previous iteration
            if hasattr(self, 'outputs'):
                self.outputs.clear()

            # Clean CUDA state for accurate measurement
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.synchronize(self.device)
            torch.cuda.reset_peak_memory_stats(self.device)

            # Measure performance without storing outputs
            time_ms = measure(runner, repeats=self.config.repeats, warmup=self.config.warmup)
            peak_bytes = torch.cuda.max_memory_allocated(self.device)

            # Store result (validation fields are None for now)
            results.append(
                BenchmarkResult(
                    name=name,
                    time_ms=time_ms,
                    gbps=bytes_moved / time_ms / 1e6,
                    bytes_moved=bytes_moved,
                    matches=None,  # Will be set in stage 2
                    max_abs_diff=None,  # Will be set in stage 2
                    peak_mem_gb=peak_bytes / 1e9,
                    extras=dict(extras),
                )
            )

        # ═══════════════════════════════════════════════════════
        # STAGE 2: CORRECTNESS VALIDATION (forward + backward)
        # ═══════════════════════════════════════════════════════
        torch.cuda.empty_cache()
        torch.cuda.synchronize(self.device)

        # Run each implementation ONCE to collect outputs and gradients
        outputs: Dict[str, torch.Tensor] = {}
        input_grads: Dict[str, torch.Tensor] = {}

        for name, (module, extras) in implementations.items():
            input_copy = self.input_tensor.clone().requires_grad_(True)
            with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
                out = module(input_copy)
                if isinstance(out, tuple):
                    out = out[0]
                loss = out.sum()
            loss.backward()

            outputs[name] = out.detach().to(torch.float32)
            input_grads[name] = input_copy.grad.detach().to(torch.float32)

        # Validate within reference groups (skip if reference doesn't exist)
        for reference_name, group_members in groups.items():
            if reference_name not in outputs:
                continue  # Skip groups where reference wasn't run

            reference_output = outputs[reference_name]
            reference_grad = input_grads[reference_name]

            # Compare each group member against the reference
            for result in results:
                if result.name not in group_members:
                    continue  # Not in this group

                if result.name == reference_name:
                    # Reference implementation matches itself
                    result.matches = True
                    result.max_abs_diff = None
                else:
                    # Compare variant against reference
                    candidate_output = outputs[result.name]
                    candidate_grad = input_grads[result.name]

                    # Check forward output difference
                    fwd_diff_tensor = (candidate_output - reference_output).abs()
                    fwd_max_diff = float(fwd_diff_tensor.max()) if fwd_diff_tensor.numel() > 0 else 0.0
                    fwd_mean_diff = float(fwd_diff_tensor.mean()) if fwd_diff_tensor.numel() > 0 else 0.0

                    # Check backward gradient difference
                    bwd_diff_tensor = (candidate_grad - reference_grad).abs()
                    bwd_max_diff = float(bwd_diff_tensor.max()) if bwd_diff_tensor.numel() > 0 else 0.0
                    bwd_mean_diff = float(bwd_diff_tensor.mean()) if bwd_diff_tensor.numel() > 0 else 0.0

                    result.max_abs_diff = fwd_max_diff
                    result.mean_abs_diff = fwd_mean_diff
                    result.diagnostics['fwd_max_diff'] = fwd_max_diff
                    result.diagnostics['fwd_mean_diff'] = fwd_mean_diff
                    result.diagnostics['bwd_max_diff'] = bwd_max_diff
                    result.diagnostics['bwd_mean_diff'] = bwd_mean_diff
                    result.diagnostics['grad_match'] = bwd_max_diff <= self.tolerance
                    result.matches = (fwd_max_diff <= self.tolerance) and (bwd_max_diff <= self.tolerance)

                    # Add numerical diagnostics when there's a mismatch
                    if not result.matches:
                        # Forward diagnostics
                        if fwd_max_diff > self.tolerance:
                            result.diagnostics['fwd_ref_min'] = float(reference_output.min())
                            result.diagnostics['fwd_ref_max'] = float(reference_output.max())
                            result.diagnostics['fwd_test_min'] = float(candidate_output.min())
                            result.diagnostics['fwd_test_max'] = float(candidate_output.max())

                            # Sample forward mismatches
                            if fwd_diff_tensor.numel() > 0:
                                flat_diff = fwd_diff_tensor.flatten()
                                flat_ref = reference_output.flatten()
                                flat_test = candidate_output.flatten()
                                top_k = min(3, flat_diff.numel())
                                _, top_indices = torch.topk(flat_diff, top_k)

                                samples = []
                                for idx in top_indices:
                                    idx_val = int(idx)
                                    ref_val = float(flat_ref[idx_val])
                                    test_val = float(flat_test[idx_val])
                                    multi_idx = []
                                    remaining = idx_val
                                    for dim in reversed(candidate_output.shape):
                                        multi_idx.insert(0, remaining % dim)
                                        remaining //= dim
                                    samples.append((tuple(multi_idx), ref_val, test_val))
                                result.diagnostics['fwd_sample_diffs'] = samples

                        # Backward diagnostics
                        if bwd_max_diff > self.tolerance:
                            result.diagnostics['bwd_ref_min'] = float(reference_grad.min())
                            result.diagnostics['bwd_ref_max'] = float(reference_grad.max())
                            result.diagnostics['bwd_test_min'] = float(candidate_grad.min())
                            result.diagnostics['bwd_test_max'] = float(candidate_grad.max())

                            # Sample backward mismatches
                            if bwd_diff_tensor.numel() > 0:
                                flat_diff = bwd_diff_tensor.flatten()
                                flat_ref = reference_grad.flatten()
                                flat_test = candidate_grad.flatten()
                                top_k = min(3, flat_diff.numel())
                                _, top_indices = torch.topk(flat_diff, top_k)

                                samples = []
                                for idx in top_indices:
                                    idx_val = int(idx)
                                    ref_val = float(flat_ref[idx_val])
                                    test_val = float(flat_test[idx_val])
                                    multi_idx = []
                                    remaining = idx_val
                                    for dim in reversed(candidate_grad.shape):
                                        multi_idx.insert(0, remaining % dim)
                                        remaining //= dim
                                    samples.append((tuple(multi_idx), ref_val, test_val))
                                result.diagnostics['bwd_sample_diffs'] = samples

        # Collect statistics
        stats = self._collect_group_stats(outputs, groups)

        return results, stats
