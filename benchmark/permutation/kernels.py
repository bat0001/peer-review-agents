"""Compatibility layer for benchmark kernels.

The benchmarks import from this module to keep relative imports working when
invoked as a script. The actual Triton implementations now live in
``src.kernels`` so the rest of the codebase can share them.
"""

from __future__ import annotations

from src.kernels import (  # noqa: F401 - re-export for benchmark callers
    gather,
    scatter_atomic,
    fused_gather_wgrad,
)

__all__ = [
    "gather",
    "scatter_atomic",
    "fused_gather_wgrad",
]
