"""Main entry point for permutation benchmarks."""

from __future__ import annotations

import argparse

from benchmark.permutation.base import BaseAutogradBenchmark
from benchmark.permutation.common import format_results, format_stats
from benchmark.permutation.core import add_standard_args, args_to_config, setup_environment


ALL_BENCHMARKS = [
    'gather-forward', 'gather-backward',
    'scatter-forward', 'scatter-backward',
    'scatter-addinto-forward', 'scatter-addinto-backward',
]


def main() -> None:
    """Main entry point for 6 core permutation benchmarks."""
    setup_environment()

    parser = argparse.ArgumentParser(
        description='Permutation kernel benchmarks (6 core benchmarks)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m benchmark.permutation                                   # Run all 6 benchmarks
  python -m benchmark.permutation gather-forward scatter-forward    # Run specific benchmarks
  python -m benchmark.permutation --tokens 8192 --hidden 1024       # Custom config

Six core benchmarks:
  gather-forward          - Gather kernel (no weights)
  gather-backward         - Gather autograd (no weights)
  scatter-forward         - Scatter kernel (with weights)
  scatter-backward        - Scatter autograd (with weights)
  scatter-addinto-forward - Scatter addinto kernel (mimics GEC_shared)
  scatter-addinto-backward- Scatter addinto autograd (mimics GEC_shared)
        """,
    )
    parser.add_argument(
        'benchmarks',
        nargs='*',
        default=[],
        metavar='BENCHMARK',
        help=f'which benchmarks to run (default: all 6). choices: {", ".join(ALL_BENCHMARKS)}',
    )
    add_standard_args(parser)

    args = parser.parse_args()

    # Validate benchmark names
    for b in args.benchmarks:
        if b not in ALL_BENCHMARKS:
            parser.error(f"invalid benchmark: '{b}' (choose from {', '.join(ALL_BENCHMARKS)})")

    config = args_to_config(args)

    # Default to all 6 benchmarks if none specified
    if not args.benchmarks or len(args.benchmarks) == 0:
        benchmarks_to_run = ALL_BENCHMARKS
    else:
        benchmarks_to_run = args.benchmarks

    print(
        f'[benchmark] '
        f'tokens={config.num_tokens:,} hidden={config.hidden} '
        f'G={config.granularity} E={config.expansion} experts={config.num_experts} capacity={config.capacity} '
        f'dtype=bf16 repeats={config.repeats} warmup={config.warmup} '
        f'benchmarks={benchmarks_to_run}'
    )

    # Import all benchmark classes
    from benchmark.permutation.gather.benchmark import GatherForwardBenchmark
    from benchmark.permutation.gatherop.benchmark import GatherBackwardBenchmark
    from benchmark.permutation.scatter.benchmark import ScatterForwardBenchmark
    from benchmark.permutation.scatterop.benchmark import ScatterBackwardBenchmark
    from benchmark.permutation.scatter_addinto.benchmark import (
        ScatterAddIntoForwardBenchmark,
        ScatterAddIntoBackwardBenchmark,
    )

    # Build cases dict (6 fixed benchmarks)
    all_cases = {
        'gather-forward': (GatherForwardBenchmark(config), None),
        'gather-backward': (GatherBackwardBenchmark(config), None),
        'scatter-forward': (ScatterForwardBenchmark(config), None),
        'scatter-backward': (ScatterBackwardBenchmark(config), None),
        'scatter-addinto-forward': (ScatterAddIntoForwardBenchmark(config), None),
        'scatter-addinto-backward': (ScatterAddIntoBackwardBenchmark(config), None),
    }

    case_titles = {
        'gather-forward': 'GATHER FORWARD (kernel only, no weights)',
        'gather-backward': 'GATHER BACKWARD (forward+backward autograd, no weights)',
        'scatter-forward': 'SCATTER FORWARD (kernel only, with weights)',
        'scatter-backward': 'SCATTER BACKWARD (forward+backward autograd, with weights)',
        'scatter-addinto-forward': 'SCATTER ADDINTO FORWARD (kernel only, mimics GEC_shared)',
        'scatter-addinto-backward': 'SCATTER ADDINTO BACKWARD (forward+backward autograd, mimics GEC_shared)',
    }

    # Filter to requested benchmarks
    cases = {k: all_cases[k] for k in benchmarks_to_run}

    # Run all cases
    for key in cases.keys():
        bm, weight_grads = cases[key]

        # Check if this is an autograd benchmark (gather-backward or scatter-backward)
        if isinstance(bm, BaseAutogradBenchmark):
            results, stats = bm.run_autograd_case()
        else:
            results, stats = bm.run_single_case(weight_grads=weight_grads)

        title = case_titles.get(key, f'[{key}]')
        print('=' * 88)
        print(f' {title} '.center(88, '='))
        print('=' * 88)

        # Get both performance and validation tables
        perf_table, val_table = format_results(results)

        # Print performance table
        print(perf_table)

        # Print validation table if it exists
        if val_table:
            print()
            print(val_table)

        print('=' * 88)

        stats_block = format_stats(stats)
        if stats_block:
            print()
            print('INFO:', stats_block)
        print()


if __name__ == '__main__':
    main()