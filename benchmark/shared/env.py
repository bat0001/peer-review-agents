"""Environment setup used by benchmarks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import torch


def setup_environment() -> None:
    """Prepare sys.path, TRITON env vars, and CUDA availability."""
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    os.environ.setdefault('TRITON_PRINT_AUTOTUNE', '1')

    if not torch.cuda.is_available():
        raise SystemError('CUDA device required for benchmarks')
