"""Core infrastructure for permutation benchmarks (shim to benchmark.shared)."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from benchmark.shared.compile import TorchCompileManager
from benchmark.shared.config import BenchmarkConfig, add_standard_args, args_to_config, get_tolerance
from benchmark.shared.env import setup_environment


class ImplementationRegistry:
    """Registry for benchmark implementations."""

    def __init__(self) -> None:
        self.implementations: Dict[str, tuple[Callable[[], None], Callable, Dict[str, float | bool]]] = {}

    def register(
        self,
        name: str,
        runner: Callable[[], None],
        output_fn: Callable,
        extras: Optional[Dict[str, float | bool]] = None,
    ) -> None:
        """Register an implementation."""
        self.implementations[name] = (runner, output_fn, extras or {})

    def items(self):
        """Iterate over implementations."""
        return self.implementations.items()

    def get_reference_name(self) -> str:
        """Get the name of the reference implementation (typically 'torch')."""
        return 'torch'

    def __contains__(self, name: str) -> bool:
        return name in self.implementations

    def __getitem__(self, name: str):
        return self.implementations[name]


__all__ = [
    'BenchmarkConfig',
    'setup_environment',
    'add_standard_args',
    'get_tolerance',
    'args_to_config',
    'TorchCompileManager',
    'ImplementationRegistry',
]
