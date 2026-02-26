"""MLP-specific benchmark entry points."""

from benchmark.mlp.__main__ import main
from benchmark.mlp.base import MLPAutogradBenchmark, MLPBenchmark

__all__ = [
    'main',
    'MLPBenchmark',
    'MLPAutogradBenchmark',
]
