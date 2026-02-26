"""Shared configuration helpers for benchmark CLI parsing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional

import torch


@dataclass
class BenchmarkConfig:
    """Core benchmark configuration (routing-agnostic)."""

    num_tokens: int
    hidden: int
    granularity: int  # G: d_ff / d_expert
    expansion: int    # E: routed expert expansion
    repeats: int
    warmup: int
    device: torch.device = torch.device('cuda')
    num_experts: Optional[int] = None
    density: Optional[float] = None  # Legacy/compat convenience for scripts that still expect density

    @property
    def capacity(self) -> int:
        """Compute expert capacity: k = num_tokens // E."""
        return self.num_tokens // self.expansion

    def validate(self) -> None:
        """Validate configuration parameters."""
        G = self.granularity
        if G <= 0 or (G & (G - 1)) != 0:
            raise ValueError(f'granularity must be a power of 2, got {G}')

        if self.expansion <= 0:
            raise ValueError(f'expansion must be positive, got {self.expansion}')


@dataclass
class MLPBenchmarkConfig(BenchmarkConfig):
    """Benchmark configuration with routing flags for MLP benchmarks only."""

    routing_mode: str = 'topk'  # 'topk' or 'threshold'
    gec_config: str = 'all'     # 'all', 'gec', or 'gec_shared'


def setup_base_parser(parser: argparse.ArgumentParser) -> None:
    """Add common benchmark arguments."""
    parser.add_argument('--tokens', type=int, default=131072, help='number of tokens (B*T)')
    parser.add_argument('--hidden', type=int, default=768, help='hidden dimension (n_embd)')
    parser.add_argument(
        '-G',
        '--granularity',
        type=int,
        default=2,
        dest='granularity',
        help='G: granularity (d_ff / d_expert), must be power of 2',
    )
    parser.add_argument(
        '-E',
        '--expansion',
        type=int,
        default=8,
        dest='expansion',
        help='E: routed expert expansion rate',
    )
    parser.add_argument('--repeats', type=int, default=50, help='number of timing iterations')
    parser.add_argument('--warmup', type=int, default=10, help='number of warmup iterations')


def add_standard_args(parser: argparse.ArgumentParser) -> None:
    """Add routing-agnostic benchmark arguments."""
    setup_base_parser(parser)


def add_routing_args(parser: argparse.ArgumentParser) -> None:
    """Add routing-only flags used by MLP benchmarks."""
    parser.add_argument(
        '--routing-mode',
        type=str,
        default='topk',
        dest='routing_mode',
        choices=['topk', 'threshold'],
        help='routing mode for GEC models',
    )
    parser.add_argument(
        '--config',
        type=str,
        default='all',
        dest='gec_config',
        choices=['all', 'gec', 'gec_shared'],
        help='GEC configuration: all (both), gec (no shared), gec_shared (with shared)',
    )


def args_to_config(args: argparse.Namespace) -> BenchmarkConfig:
    """Convert argparse Namespace to routing-agnostic BenchmarkConfig."""
    config = BenchmarkConfig(
        num_tokens=args.tokens,
        hidden=args.hidden,
        granularity=args.granularity,
        expansion=args.expansion,
        repeats=args.repeats,
        warmup=args.warmup,
        num_experts=args.granularity * args.expansion,
        density=1.0 / args.expansion if args.expansion != 0 else None,
    )
    config.validate()
    return config


def args_to_mlp_config(args: argparse.Namespace) -> MLPBenchmarkConfig:
    """Convert argparse Namespace to MLPBenchmarkConfig with routing flags."""
    config = MLPBenchmarkConfig(
        num_tokens=args.tokens,
        hidden=args.hidden,
        granularity=args.granularity,
        expansion=args.expansion,
        repeats=args.repeats,
        warmup=args.warmup,
        routing_mode=getattr(args, 'routing_mode', 'topk'),
        gec_config=getattr(args, 'gec_config', 'all'),
        num_experts=args.granularity * args.expansion,
        density=1.0 / args.expansion if args.expansion != 0 else None,
    )
    config.validate()
    return config


def get_tolerance() -> float:
    """Numerical tolerance for mixed precision (BF16)."""
    return 1e-2
