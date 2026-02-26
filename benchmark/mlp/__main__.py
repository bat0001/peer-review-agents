"""Main entry point for MLP benchmarks - dispatcher for ExpertEngine benchmarks."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Dispatcher for ExpertEngine benchmarks."""

    parser = argparse.ArgumentParser(
        description='ExpertEngine benchmarks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage:
  python -m benchmark.mlp [operation] [options]

Operations:
  all        Run both forward and backward benchmarks (default)
  forward    Forward pass benchmark only
  backward   Forward+backward pass benchmark only

Options (apply to all operations):
  --routing-mode {topk,threshold}  Routing mode (default: topk)
  --tokens N                       Number of tokens (default: 131072)
  --hidden N                       Hidden dimension (default: 768)
  -G, --granularity N              Granularity G (default: 2)
  -E, --expansion N                Expansion E (default: 8)
  --repeats N                      Timing iterations (default: 50)
  --warmup N                       Warmup iterations (default: 10)

Examples:

  # Run all benchmarks (forward + backward) with defaults
  python -m benchmark.mlp

  # Run all benchmarks with custom params
  python -m benchmark.mlp --tokens 2048 --hidden 256 -G 2 -E 4

  # Forward pass only
  python -m benchmark.mlp forward

  # Forward pass with threshold routing (inference mode)
  python -m benchmark.mlp forward --routing-mode threshold

  # Backward pass with topk routing (training)
  python -m benchmark.mlp backward --routing-mode topk

Each benchmark tests recipes (scatter × engine × wrapper × compile):
  - index_add: PyTorch index_add_ scatter backend
  - index_add-compiled: torch.compile version
  - csr: CSR kernel scatter backend
  - csr-compiled: torch.compile version

For each recipe, tests both:
  - is_shared=False (GEC config)
  - is_shared=True (GEC_shared config)

CSR implementations validate against index_add (reference).

See benchmark/mlp/README.md for detailed documentation.
        """,
    )

    # Check if first argument is an operation keyword
    # If not, default to 'all' and treat all args as options
    operation = 'all'
    argv_to_parse = sys.argv[1:]

    if argv_to_parse and argv_to_parse[0] in ['forward', 'backward', 'all']:
        operation = argv_to_parse[0]
        remaining = argv_to_parse[1:]
    else:
        # No operation specified, use all args as options for 'all'
        remaining = argv_to_parse

    # Dispatch to specific benchmark(s)
    if operation == 'forward':
        from benchmark.mlp.forward import main as forward_main
        # Replace argv to pass remaining args
        sys.argv = ['benchmark.mlp.forward'] + remaining
        forward_main()
    elif operation == 'backward':
        from benchmark.mlp.backward import main as backward_main
        sys.argv = ['benchmark.mlp.backward'] + remaining
        backward_main()
    elif operation == 'all':
        # Run both forward and backward
        print("\n" + "="*80)
        print("Running FORWARD benchmark")
        print("="*80)
        from benchmark.mlp.forward import main as forward_main
        sys.argv = ['benchmark.mlp.forward'] + remaining
        forward_main()

        print("\n\n" + "="*80)
        print("Running BACKWARD benchmark")
        print("="*80)
        from benchmark.mlp.backward import main as backward_main
        sys.argv = ['benchmark.mlp.backward'] + remaining
        backward_main()


if __name__ == '__main__':
    main()
