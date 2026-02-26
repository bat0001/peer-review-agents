# Permutation Benchmarks (Agent Notes)

The microbenchmarks under `benchmark/permutation/` exercise Triton, manual, and eager torch implementations of the expert-choice gather/scatter path. They are written to be copy/paste templates; keep the pattern intact so new agents can drop in kernels or modify shapes without rediscovering gotchas.

## Six Core Benchmarks

The benchmark suite consists of **6 fixed benchmarks**:

1. **gather-forward** - Gather kernel (forward only, **no weights**)
2. **gather-backward** - Gather autograd (forward+backward, **no weights**)
3. **scatter-forward** - Scatter kernel (forward only, **with weights**)
4. **scatter-backward** - Scatter autograd (forward+backward, **with weights**)
5. **scatter-addinto-forward** - Scatter addinto kernel (mimics **GEC_shared** pattern)
6. **scatter-addinto-backward** - Scatter addinto autograd (mimics **GEC_shared** pattern)

**Key design decisions:**
- **Gather = no weights**: Simple indexing `tokens[indices]`
- **Scatter = with weights**: Weighted aggregation `index_add(weighted_values)`
- **Scatter AddInto = GEC_shared pattern**: Accumulate routed outputs into pre-existing buffer
- **All implementations test both raw and compiled versions** (via `torch.compile`)
- **Forward = kernel only** (no autograd wrapper)
- **Backward = forward+backward autograd** (wrapped in `torch.autograd.Function`)

## Architecture

**Class-based design**: Each benchmark is a class inheriting from `BaseBenchmark` with three core methods:
- `setup_data()`: Create input tensors once, reused by all implementations
- `create_implementations()`: Return dict of `(runner, output_fn, extras)` tuples
- `compute_bytes()`: Calculate memory bandwidth for this operation

**Orchestration in `__main__.py`**: All benchmark running logic lives in `__main__.py`. Benchmark classes are pure data + implementation factories with no orchestration logic.

**Shared utilities**: CLI parsing, timing, and formatting come from `benchmark/shared/`. The permutation CLI uses only `add_standard_args` (tokens/hidden/G/E/repeats/warmup); routing flags live exclusively in MLP benchmarks.

## Scatter Forward Implementations

The `scatter-forward` benchmark consolidates **all scatter implementations** in a single table:

**Reference implementations:**
- `torch` (reference) - FP32 accumulation via `.index_add_()` (matches Triton kernel semantics)
- `torch-bf16` - Native BF16 accumulation (shows PyTorch default behavior)
- `torch-compile` / `torch-bf16-compile` - Compiled versions

**Triton implementations:**
- `triton-atomic` - Triton atomic scatter from `src/kernels/balanced.py`
- `sequential` - Token-parallel scatter (no atomics) from `src/kernels/sequential.py`
- `csr-scatter` - CSR format token-parallel scatter from `src/kernels/csr.py`
- `buffer-reduce` - Dense buffer approach (for comparison)
- All have `-compile` variants

**Validation**: All implementations validate against `torch` (FP32 accumulation). The `torch-bf16` baseline shows the precision difference from BF16 vs FP32 accumulation (~3-6e-2).

## Accumulation Precision

Our Triton kernels use **FP32 accumulation** internally for numerical stability:
```python
acc = tl.zeros([BLOCK_X], dtype=tl.float32)  # FP32 accumulator
x = tl.load(expert_ptr, ...).to(tl.float32)
acc += x * w
tl.store(out_ptr, acc.to(token_out.dtype.element_ty), ...)  # Downcast to BF16
```

This differs from PyTorch's `index_add_` which accumulates in the output tensor's dtype (BF16). The `torch` reference uses explicit FP32 accumulation to match kernel behavior:
```python
out = self.shared_out.float()  # FP32 accumulator
weighted = self.expert_out_flat.float() * self.weights_flat_fp32
out.index_add_(0, self.indices, weighted)
return out.to(torch.bfloat16)  # Downcast on return
```

See `memory/design/dtype_handling.md` for detailed rationale.

## Data plumbing

- Always synthesise tensors once in `setup_data()` so they can be reused by every implementation. Typical shapes:
  - Tokens: `(num_tokens, hidden)`
  - Expert activations: `(num_experts, capacity, hidden)` where `capacity = floor(density * num_tokens)`
  - Router indices: `num_experts * capacity`, returned by `src.kernels.build_expert_major_indices`
  - Weights (scatter only): `num_experts * capacity` sigmoid weights; store as FP32 and reshape with `view(-1, 1)` when broadcasting.
- Keep both BF16/FP16 tensors and any FP32 "workspace" views around if the maths requires higher precision. Let PyTorch handle promotion (e.g. `torch.mul(bf16_tensor, fp32_vector)`) instead of copying to FP32 by hand.

## Implementation registry pattern

`create_implementations()` returns a dict mapping name to 3-tuple `(runner, output_fn, extras)`:

```python
{
    'torch': (runner_fn, output_fn, {}),
    'torch-compile': (runner_fn, output_fn, {'compiled': True}),
    'triton': (runner_fn, output_fn, {'triton': True}),
    'triton-compile': (runner_fn, output_fn, {'triton': True, 'compiled': True}),
    # ...
}
```

- `runner()`: Performs the timed work (zero buffers, launch kernel). Must not allocate new long-lived tensors during every call; zero-in-place instead.
- `output_fn()`: Returns the tensor used for correctness checks. Keep it side-effect free. For autograd benches, returns `(forward, grad)` tuple.
- `extras`: Metadata dict (buffer size, compiled flag, etc.) shown in result table via `BenchmarkResult.extras`.

When you add a new kernel, create both closures explicitly so timing and correctness stay separated. **Always add both raw and compiled versions.**

## Reference and tolerances

- Base class computes reference output once via the 'torch' implementation, then casts to FP32: `reference = torch_impl(...).detach().to(torch.float32)`.
- Every candidate output is cast to FP32 before diffing. This avoids dtype noise while keeping kernels in mixed precision.
- All benchmarks use mixed precision (BF16) with fixed tolerance of 1e-2. Input tensors are explicitly cast to BF16 for consistent behavior.

## Gather Forward Implementations

The `gather-forward` benchmark reports two families of implementations:

- `torch` / `torch-compile` – direct indexing on the token buffer (baseline)
- `triton` / `triton-compile` – slot-parallel gather from `src/kernels/balanced.py`

**Note**: CSR is NOT in gather-forward because the CSR kernel (`_csr_scatter_sum`) is a scatter operation, not gather. CSR only appears in gather autograd (see below).

## Gather Autograd Implementations (gatherop)

The `gatherop` benchmark tests forward+backward (autograd) for gather operations:

- `torch` / `torch-compile` – direct indexing with PyTorch autograd
- `balanced-op` / `balanced-op-compile` – custom gather op from `src/ops`
- `csr` / `csr-compile` – CSR-based gather op where backward uses token-parallel CSR scatter kernel

**Why CSR in gatherop?** The CSR gather op (`src/ops/csr.csr_gather`) performs:
- **Forward**: Regular gather (standard PyTorch indexing)
- **Backward**: Token-parallel CSR scatter using `_csr_scatter_sum` kernel

This leverages the fact that gather's backward is a scatter operation. The CSR scatter kernel parallelizes across tokens (instead of expert slots), which can be more efficient when multiple expert slots scatter to the same token.

## Scatter Autograd Implementations (scatterop)

The `scatterop` benchmark tests forward+backward (autograd) for scatter operations:

- `torch` / `torch-compile` – index_add with PyTorch autograd
- `balanced-op` / `balanced-op-compile` – custom scatter op using triton-atomic scatter forward with fused backward
- `csr-scatter-op` / `csr-scatter-op-compile` – CSR scatter autograd using token-parallel CSR scatter forward

**Why CSR in scatterop?** The CSR scatter op (`src/ops/csr.csr_scatter_sum`) performs:
- **Forward**: Token-parallel CSR scatter using `_csr_scatter_sum` kernel
- **Backward**: Regular gather to expert slots + weight gradients

The CSR forward can be more efficient than atomic scatter when parallelizing across tokens, especially when expert buffers scatter to overlapping tokens.

## Timing and memory stats

- Base class uses `benchmark.permutation.common.measure` for timing with CUDA synchronisations and warmups.
- `torch.cuda.reset_peak_memory_stats(device)` is called before timing each implementation.
- Results accumulate in `BenchmarkResult` and pretty-print via `format_results` / `format_stats`.

## CLI usage

Run specific benchmarks or all 6:

```bash
# Run all 6 benchmarks (default)
python -m benchmark.permutation

# Run specific benchmarks
python -m benchmark.permutation gather-forward scatter-forward

# Run addinto benchmarks (GEC_shared pattern)
python -m benchmark.permutation scatter-addinto-forward scatter-addinto-backward

# Custom configuration
python -m benchmark.permutation --tokens 8192 --hidden 1024 -G 2 -E 16
```

The CLI prints effective configuration (tokens, hidden, experts, density, dtype, repeats, warmup) before running for reproducibility.

## Adding new scatter implementations

To add a new scatter implementation to `scatter-forward` benchmark:

1. Add implementation in `benchmark/permutation/scatter/benchmark.py` `create_implementations()`
2. Create both raw and compiled versions (use `self.compile_manager.try_compile()`)
3. All scatter implementations should use weights and validate against `index_add` reference
4. Update this README's scatter implementations list

Example:
```python
def new_scatter_impl() -> torch.Tensor:
    # Your implementation here
    return out

implementations['new-scatter'] = (
    lambda: new_scatter_impl(),
    new_scatter_impl,
    {'weight_fused': True, 'custom_flag': True}
)

# Add compiled version
compiled = self.compile_manager.try_compile(new_scatter_impl)
if compiled:
    implementations['new-scatter-compile'] = (
        lambda: compiled(),
        compiled,
        {'weight_fused': True, 'custom_flag': True, 'compiled': True}
    )
```

## Benchmark Classes

- **GatherForwardBenchmark** (`gather/benchmark.py`) - Gather kernel, no weights, simple indexing
- **GatherBackwardBenchmark** (`gatherop/benchmark.py`) - Gather with autograd, no weights
- **ScatterForwardBenchmark** (`scatter/benchmark.py`) - All scatter implementations, with weights
- **ScatterBackwardBenchmark** (`scatterop/benchmark.py`) - Scatter with autograd, with weights
- **ScatterAddIntoForwardBenchmark** (`scatter_addinto/benchmark.py`) - Scatter addinto kernel, mimics GEC_shared
- **ScatterAddIntoBackwardBenchmark** (`scatter_addinto/benchmark.py`) - Scatter addinto autograd, mimics GEC_shared

All backward benchmarks test forward+backward autograd using `make_autograd_case()` helper from `BaseAutogradBenchmark`.

## Scatter AddInto Benchmarks (GEC_shared Pattern)

The `scatter-addinto-*` benchmarks test the GEC_shared pattern where routed expert outputs are **accumulated into** a pre-existing buffer (the weighted shared expert output) rather than scattering into zeros.

**scatter-addinto-forward** implementations:
- `torch` (reference) - `out = shared_out.clone(); out.index_add_(...)`
- `torch-compile` - Compiled version
- `sequential-addinto` - Sequential kernel with `ADD_INTO=True`
- `sequential-addinto-compile` - Compiled version
- `csr-addinto` - CSR kernel with `ACCUMULATE=1`
- `csr-addinto-compile` - Compiled version

**scatter-addinto-backward** implementations:
- `torch` / `torch-compile` - PyTorch autograd with clone + index_add
- `csr-addinto-op` / `csr-addinto-op-compile` - CSR scatter op with shared_flat/shared_weights

**Key difference from scatter-forward:**
| Aspect | scatter-forward | scatter-addinto-forward |
|--------|-----------------|-------------------------|
| Output init | `zeros(N, H)` | `shared_out.clone()` |
| Kernel flag | `ACCUMULATE=0` | `ACCUMULATE=1` |
| Use case | GEC | GEC_shared |

## Further reading

For concrete examples, inspect:
- `gather/benchmark.py` - Simple indexing pattern without weights
- `scatter/benchmark.py` - Consolidation of all scatter implementations with weights
- `gatherop/benchmark.py` - Autograd pattern for gather (no weights)
- `scatterop/benchmark.py` - Autograd pattern for scatter (with weights)
- `scatter_addinto/benchmark.py` - AddInto pattern for GEC_shared

Update this file whenever you change the benchmark structure or add new implementations.
