# Benchmark Suite

Benchmarks for routed MLPs and the underlying gather/scatter kernels.

## Layout
- `benchmark/shared/` — neutral utilities for config parsing, timing, result formatting, and environment setup. `add_standard_args` only adds kernel-agnostic flags (tokens, hidden, G, E, repeats, warmup). `add_routing_args` adds `--routing-mode/--config` and is used only by MLP benchmarks.
- `benchmark/permutation/` — four fixed kernel/autograd benchmarks (gather-forward/backward, scatter-forward/backward). The CLI is now routing-free and uses only the shared flags. Results are formatted via `benchmark.shared.results`.
- `benchmark/mlp/` — ExpertEngine forward/backward benchmarks for topk/threshold routing. Uses the shared utilities plus `add_routing_args` for routing-only CLI flags and the `MLPBenchmarkConfig`.

## Common behavior
- BF16 autocast for inputs; parameters stay FP32.
- Capacity and expert counts derived from G/E (`num_experts = G × E`, `capacity = tokens // E`).
- Validation compares FP32-cast outputs; tolerance is `1e-2` (BF16).
- GPU required; check `nvidia-smi` before running.

## Running
- Permutation kernels (routing-free CLI):
  - `python -m benchmark.permutation` (all four)
  - `python -m benchmark.permutation scatter-forward --tokens 8192 --hidden 1024 -G 2 -E 16`
- MLP benchmarks (routing flags enabled):
  - `python -m benchmark.mlp forward --routing-mode topk`
  - `python -m benchmark.mlp backward --routing-mode threshold --tokens 2048 --hidden 256 -G 2 -E 4`

## Validation and output
- Permutation: single-stage timing + correctness vs `torch` reference; peak memory recorded when available.
- MLP: two-stage run (clean timing, then grouped validation) with grouped result tables and per-group diagnostics.
