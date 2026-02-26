"""Core utilities for MLP benchmarks."""

from __future__ import annotations

import argparse

from benchmark.shared.compile import TorchCompileManager
from benchmark.shared.config import (
    BenchmarkConfig,
    MLPBenchmarkConfig,
    add_routing_args,
    add_standard_args,
    args_to_mlp_config,
    get_tolerance,
)
from benchmark.shared.env import setup_environment

__all__ = [
    'BenchmarkConfig',
    'MLPBenchmarkConfig',
    'TorchCompileManager',
    'add_standard_args',
    'add_routing_args',
    'args_to_config',
    'get_tolerance',
    'setup_environment',
    'detect_gpu',
]


def args_to_config(args: argparse.Namespace) -> MLPBenchmarkConfig:
    """Convert argparse Namespace to MLPBenchmarkConfig (keeps legacy name)."""
    return args_to_mlp_config(args)


def detect_gpu() -> str:
    """Auto-detect GPU type from supported list."""
    import torch

    gpu_name = torch.cuda.get_device_name(0).upper()

    if 'H100' in gpu_name:
        return 'H100'
    elif 'A100' in gpu_name:
        return 'A100'
    elif 'A5000' in gpu_name or 'RTX A5000' in gpu_name:
        return 'A5000'
    elif '4090' in gpu_name or 'RTX 4090' in gpu_name:
        return '4090'
    else:
        print(f'Unsupported GPU: {gpu_name}')
        print('Supported GPUs: H100, A100, A5000, RTX 4090')
        return 'unknown'
