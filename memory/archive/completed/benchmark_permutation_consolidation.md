# Permutation Benchmark Consolidation

**Completed:** 2025-11-17
**Status:** Complete and tested

## Summary

Consolidated permutation benchmarks from **12 tables to 4 core benchmarks**, merged all scatter implementations into a single table, and standardized the testing approach across all implementations.

## Motivation

The original permutation benchmarks had significant redundancy:
- 12 different benchmark tables testing similar functionality
- Scatter implementations fragmented across multiple tables
- Inconsistent reference implementations for validation
- Weight handling inconsistently applied (some had weights, some didn't)
- Multiple modes (forward-only, backward-only, forward+backward) creating combinatorial explosion

This made it difficult to compare scatter implementations and added maintenance burden.

## Changes Implemented

### 1. Consolidation: 12 tables → 4 benchmarks

**Before:** 12 tables across 4 modes
- `gather-weights` + `gather-no-weights` (2 tables)
- `scatter-dense` + `scatter-atomic` (2 tables)
- `gatherop-forward` + `gatherop-backward` + `gatherop-fwd-bwd` (3 tables)
- `scatterop-forward` + `scatterop-bwd-wgrad` + `scatterop-bwd-no-wgrad` + `scatterop-kernel-wgrad` + `scatterop-kernel-no-wgrad` (5 tables)

**After:** 4 fixed benchmarks
1. **gather-forward** - Gather kernel (forward only, no weights)
2. **gather-backward** - Gather autograd (forward+backward, no weights)
3. **scatter-forward** - Scatter kernel (forward only, with weights)
4. **scatter-backward** - Scatter autograd (forward+backward, with weights)

### 2. Key Design Decisions

**Gather = NO weights**
- Rationale: Gather is simple indexing, weights complicate unnecessarily
- Implementation: Use simple indexing `tokens[routing]` instead of `index_select()`
- Cleaner API and matches actual GEC engine usage

**Scatter = WITH weights**
- Rationale: Scatter in GEC always uses router weights
- Implementation: All scatter benchmarks include weighted aggregation
- Matches real-world usage pattern

**All implementations test raw + compiled**
- Every implementation has both base and `torch-compile` versions
- Consistent measurement of compilation overhead
- Total implementations per benchmark: 4-10 depending on complexity

**Forward = kernel only, Backward = forward+backward autograd**
- Forward benchmarks: Direct kernel calls, no autograd wrapper
- Backward benchmarks: Full `torch.autograd.Function` with forward+backward
- Removed intermediate modes (backward-only, forward-only for autograd)

### 3. Scatter Forward: All Implementations in One Table

Merged all scatter implementations into single `scatter-forward` benchmark (10 total implementations):

| Implementation | Description | Type |
|----------------|-------------|------|
| `torch` | Reference using `.index_add_()` | Atomic |
| `torch-compile` | Compiled version | Atomic |
| `triton-atomic` | Triton atomic scatter | Atomic |
| `triton-atomic-compile` | Compiled version | Atomic |
| `sequential` | Token-parallel (no atomics) | Sequential |
| `sequential-compile` | Compiled version | Sequential |
| `csr-scatter` | **NEW** CSR format token-parallel | Sequential |
| `csr-scatter-compile` | Compiled version | Sequential |
| `buffer-reduce` | Dense buffer approach | Buffered |
| `buffer-reduce-compile` | Compiled version | Buffered |

**All validate against same `torch` (index_add) reference** for consistency.

### 4. File Changes

**Core refactoring:**
- `benchmark/permutation/__main__.py` - Removed mode system, fixed 4 benchmarks
- `benchmark/permutation/gather/benchmark.py` - Renamed to `GatherForwardBenchmark`, removed weights, used simple indexing
- `benchmark/permutation/scatter/benchmark.py` - Merged `DenseScatterBenchmark` + `AtomicScatterBenchmark`, added CSR
- `benchmark/permutation/gatherop/benchmark.py` - Renamed to `GatherBackwardBenchmark`, removed modes
- `benchmark/permutation/scatterop/benchmark.py` - Renamed to `ScatterBackwardBenchmark`, removed modes

**Supporting updates:**
- All `__init__.py` files updated with new class names
- `benchmark/permutation/README.md` updated with new 4-benchmark structure

### 5. CSR Scatter Integration

Added CSR (Compressed Sparse Row) scatter implementation to scatter-forward benchmark:
- Token-parallel approach using CSR format from `src/kernels/csr.py`
- Uses `build_slot_indices()` to convert expert-major indices to token-major CSR
- Launches `_csr_scatter_sum` Triton kernel with token-parallel execution
- Avoids atomic operations through read-once write-once pattern
- Both raw and compiled versions included

## Results

**Verified working:**
- ✅ All 4 benchmarks execute correctly
- ✅ Gather-forward: 4 implementations (torch, torch-compile, triton, triton-compile)
- ✅ Gather-backward: 4 implementations with autograd validation
- ✅ Scatter-forward: 10 implementations in single table
- ✅ Scatter-backward: 4 implementations with autograd validation
- ✅ All implementations validate against correct reference
- ✅ CSR scatter successfully integrated and benchmarked

**Performance (scatter-forward on small config):**
```
torch                 |     0.080 ms |  52.51 GB/s  (reference)
torch-compile         |     0.296 ms |  14.17 GB/s
triton-atomic         |     0.163 ms |  25.68 GB/s
triton-atomic-compile |     0.215 ms |  19.55 GB/s
sequential            |     0.150 ms |  27.96 GB/s
sequential-compile    |     0.186 ms |  22.57 GB/s
csr-scatter           |     0.157 ms |  26.77 GB/s  (NEW)
csr-scatter-compile   |     0.179 ms |  23.41 GB/s  (NEW)
buffer-reduce         |     0.165 ms |  25.36 GB/s
buffer-reduce-compile |     0.180 ms |  23.27 GB/s
```

All scatter implementations show expected differences due to atomic rounding (max Δ = 3.12e-02, within tolerance).

## Benefits

1. **Simpler mental model**: 4 fixed benchmarks vs 12 tables with mode selection
2. **Easy comparison**: All scatter implementations in one table
3. **Consistent validation**: All scatter impls validate against same reference
4. **Clear semantics**: gather=no weights, scatter=with weights
5. **Compilation overhead visible**: Every implementation has compiled version
6. **Extensible**: Easy to add new scatter implementations to single table
7. **CSR integration**: New token-parallel scatter approach now benchmarked

## CLI Usage

```bash
# Run all 4 benchmarks (default)
python -m benchmark.permutation

# Run specific benchmarks
python -m benchmark.permutation gather-forward scatter-forward

# Custom configuration
python -m benchmark.permutation --tokens 8192 --hidden 1024
```

## Future Work

- Consider adding more scatter variants (e.g., scatter2scatter when implemented)
- May want to benchmark CSR vs index_add on different hardware
- Consider adding gather variants with different indexing patterns
- Could add bandwidth-optimal reference implementations

## Related Files

- Implementation: `benchmark/permutation/`
- Documentation: `benchmark/permutation/README.md`
- CSR kernel: `src/kernels/csr.py`
- Sequential kernel: `src/kernels/sequential.py`
- Atomic scatter kernel: `src/kernels/balanced.py`
