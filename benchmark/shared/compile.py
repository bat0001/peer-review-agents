"""torch.compile helper used by benchmarks."""

from __future__ import annotations

from typing import Callable, Dict, Optional

import torch


class TorchCompileManager:
    """Manages torch.compile availability and wrapping."""

    def __init__(self) -> None:
        self.available = hasattr(torch, 'compile')
        self.failures = 0
        self.successes = 0

    def try_compile(
        self,
        kernel: Callable,
        test_fn: Optional[Callable[[], None]] = None,
    ) -> Optional[Callable]:
        """
        Attempt to compile a kernel.

        Args:
            kernel: The function to compile
            test_fn: Optional test function to validate compilation

        Returns:
            Compiled kernel if successful, None otherwise
        """
        if not self.available:
            return None

        try:
            compiled = torch.compile(kernel)  # type: ignore[misc]
            if test_fn is not None:
                test_fn()
                torch.cuda.synchronize()
            self.successes += 1
            return compiled
        except Exception:
            self.failures += 1
            return None

    def get_stats(self) -> Dict[str, float]:
        """Get compilation statistics."""
        return {
            'available': 1.0 if self.available else 0.0,
            'failures': float(self.failures),
        }
