"""Scatter AddInto benchmarks (mimics GEC_shared pattern)."""

from benchmark.permutation.scatter_addinto.benchmark import (
    ScatterAddIntoForwardBenchmark,
    ScatterAddIntoBackwardBenchmark,
)

__all__ = ['ScatterAddIntoForwardBenchmark', 'ScatterAddIntoBackwardBenchmark']
