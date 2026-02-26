"""Shared utilities for engine benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import torch
import torch.nn as nn


@dataclass
class Recipe:
    """A recipe is a combination of scatter, engine, wrapper, and compile options.

    Components:
    - scatter: 'index_add', 'index_add_fp32', 'csr', 'csr_optimized' (future: 'triton_atomic', ...)
    - engine: 'padded' (current, only one exists), (future: 'scattermoe', ...)
    - wrapper: 'default' (current, only one exists), (future: 'stream', ...)
    - compiled: True/False
    """
    name: str
    scatter: str
    engine: str = 'padded'
    wrapper: str = 'default'
    compiled: bool = False


# Current recipes: 3 scatters × 1 engine × 1 wrapper × 2 compile = 6
DEFAULT_RECIPES = [
    Recipe('index_add', scatter='index_add', compiled=False),
    Recipe('index_add-compiled', scatter='index_add', compiled=True),
    Recipe('csr', scatter='csr', compiled=False),
    Recipe('csr-compiled', scatter='csr', compiled=True),
    Recipe('csr_optimized', scatter='csr_optimized', compiled=False),
    Recipe('csr_optimized-compiled', scatter='csr_optimized', compiled=True),
]


def init_engine_weights(engine: nn.Module) -> None:
    """Initialize engine weights with small random values."""
    nn.init.normal_(engine.router.weight, std=0.02)
    for w1, w2 in zip(engine.expert_weight1, engine.expert_weight2):
        nn.init.normal_(w1, std=0.02)
        nn.init.normal_(w2, std=0.02)


def warmup_threshold_cutoffs(engine: nn.Module, input_tensor: torch.Tensor, iterations: int = 10) -> None:
    """Populate cutoff EMAs by running topk iterations.

    Simulates training to establish reasonable cutoff values before
    testing threshold mode.
    """
    engine.train()
    with torch.no_grad():
        for _ in range(iterations):
            engine.forward_topk(input_tensor, layer_idx=0, is_shared=False)


def get_is_shared_list(gec_config: str) -> List[bool]:
    """Map gec_config string to is_shared boolean list."""
    if gec_config == 'all':
        return [False, True]
    elif gec_config == 'gec':
        return [False]
    elif gec_config == 'gec_shared':
        return [True]
    return [False, True]  # fallback


def get_implementation_groups(gec_config: str) -> Dict[str, List[str]]:
    """Build implementation groups based on config.

    Returns groups where first entry is reference, others validate against it.
    """
    groups = {}
    if gec_config in ['all', 'gec']:
        groups['index_add-gec'] = [
            'index_add-gec', 'csr-gec', 'csr_optimized-gec',
            'index_add-gec-compiled', 'csr-gec-compiled', 'csr_optimized-gec-compiled'
        ]
    if gec_config in ['all', 'gec_shared']:
        groups['index_add-shared'] = [
            'index_add-shared', 'csr-shared', 'csr_optimized-shared',
            'index_add-shared-compiled', 'csr-shared-compiled', 'csr_optimized-shared-compiled'
        ]
    return groups


def shared_label(is_shared: bool) -> str:
    """Convert is_shared boolean to label string."""
    return 'shared' if is_shared else 'gec'
