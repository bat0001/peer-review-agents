"""Shared helpers for permutation benchmarks (shim to benchmark.shared.results)."""

from __future__ import annotations

from benchmark.shared.results import (
    BenchmarkResult,
    format_results,
    format_stats,
    measure,
    render_table as _render_table,
)

__all__ = [
    'BenchmarkResult',
    'format_results',
    'format_stats',
    'measure',
    '_render_table',
]


def measure_with_memory(fn, device: torch.device, *, repeats: int = 50, warmup: int = 10) -> tuple[float, float]:
    """
    Measure runtime and peak memory for a function.

    Args:
        fn: Function to benchmark
        device: CUDA device for memory measurement
        repeats: Number of repeats
        warmup: Number of warmup iterations

    Returns:
        (time_ms, peak_mem_gb) tuple
    """
    torch.cuda.reset_peak_memory_stats(device)
    time_ms = measure(fn, repeats=repeats, warmup=warmup)
    peak_bytes = torch.cuda.max_memory_allocated(device)
    return time_ms, peak_bytes / 1e9


__all__ = ['BenchmarkResult', 'measure', 'measure_with_memory', 'format_results', 'format_stats']
