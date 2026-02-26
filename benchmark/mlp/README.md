# MLP Benchmarks

Performance and correctness benchmarks for ExpertEngine (GEC's routed expert computation core).

## Quick Start

```bash
# Forward pass with top-k routing (training mode)
python -m benchmark.mlp forward --routing-mode topk

# Forward pass with threshold routing (inference mode)
python -m benchmark.mlp forward --routing-mode threshold

# Backward pass with top-k routing (training)
python -m benchmark.mlp backward --routing-mode topk

# Backward pass with threshold routing (dual-path training)
python -m benchmark.mlp backward --routing-mode threshold

# Custom configuration
python -m benchmark.mlp forward --routing-mode topk --tokens 2048 --hidden 256 -G 2 -E 4
```

## Architecture

The benchmark uses a **composition pattern** matching the model architecture:

```
ExpertEngine (routing + expert computation)
    ↓ returns (h_flat, indices, metrics)
Scatter Backend (aggregation: index_add or CSR)
    ↓ output
```

## Output Tables

**16 Tables** = 8 cases × 2 table types (performance + validation)

Each case (routing_mode × pass × config) produces 2 tables:
- **Performance table**: kernel, time (ms), GB/s, GB moved, peak (GB), match
- **Validation table**: kernel, max|Δ|, fwd_diff, grad_diff, etc.

**8 Cases** organized by:

| # | Routing | Pass | Config |
|---|---------|------|--------|
| 1 | topk | forward | gec |
| 2 | topk | forward | gec_shared |
| 3 | topk | backward | gec |
| 4 | topk | backward | gec_shared |
| 5 | threshold | forward | gec |
| 6 | threshold | forward | gec_shared |
| 7 | threshold | backward | gec |
| 8 | threshold | backward | gec_shared |

## Recipes

Within each table, rows are **recipes** - combinations of:

| Component | Current | Future |
|-----------|---------|--------|
| **Scatter** | index_add, index_add_fp32, csr, csr_optimized | triton_atomic, ... |
| **Engine** | padded (current) | scattermoe-style, ... |
| **Wrapper** | default (current) | stream/overlap, ... |
| **Compile** | yes, no | - |

Current recipes (4 per table):
```
index_add           - PyTorch index_add_ scatter
index_add-compiled  - torch.compile version
csr                 - CSR kernel scatter
csr-compiled        - torch.compile version
```

**Validation**: CSR implementations are validated against index_add (reference).

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--routing-mode` | `topk` | Routing mode: `topk` (training) or `threshold` (inference) |
| `--tokens` | `131072` | Number of tokens (B×T) |
| `--hidden` | `768` | Hidden dimension (n_embd) |
| `-G`, `--granularity` | `2` | G: granularity (d_ff / d_expert), must be power of 2 |
| `-E`, `--expansion` | `8` | E: routed expert expansion rate |
| `--repeats` | `50` | Number of timing iterations |
| `--warmup` | `10` | Number of warmup iterations |

**Note**: Number of experts is computed as `num_experts = G × E` automatically.

## Precision

All benchmarks run in **mixed precision mode** using BF16 autocast with FP32 master tensors. This matches the training configuration and provides optimal performance with numerical stability.

## Routing Modes

### Top-k Routing (Training)

**Purpose**: Benchmark training-time routing with global top-k selection per expert.

**Characteristics:**
- Global top-k selection (each expert selects exactly k tokens)
- Perfect load balancing (k = n_tokens / E)
- Non-causal (needs full batch)
- Fully differentiable
- Faster (batched operations)

**Usage:**
```bash
python -m benchmark.mlp forward --routing-mode topk
python -m benchmark.mlp backward --routing-mode topk
```

### Threshold Routing (Inference)

**Purpose**: Benchmark inference-time routing using learned thresholds.

**Characteristics:**
- Per-token threshold checking (router_logit > cutoff_ema)
- Approximate load balancing (depends on cutoffs)
- Causal (token-by-token processing)
- Can be used with gradients (dual-path training scenario)
- Slower (~3-5x) but enables autoregressive generation

**Cutoff warmup:**
- Both benchmarks run 10 topk iterations to populate cutoff_ema before testing threshold mode
- This simulates training warmup and ensures reasonable cutoff values

**Usage:**
```bash
# Forward pass (inference mode)
python -m benchmark.mlp forward --routing-mode threshold

# Backward pass (dual-path training scenario)
python -m benchmark.mlp backward --routing-mode threshold
```

## Comparison: topk vs threshold

| Aspect | Topk (Training) | Threshold (Inference) |
|--------|----------------|----------------------|
| **Selection** | Global top-k per expert | Per-token threshold check |
| **Load Balance** | Perfect (exactly k per expert) | Approximate (k±α%) |
| **Causality** | Non-causal (needs full batch) | Causal (token-by-token) |
| **Backward** | ✅ Supported | ✅ Supported (dual-path) |
| **Performance** | Faster (batched ops) | ~3-5x slower |
| **Use Case** | Training, batched inference | Autoregressive generation |

## is_shared Parameter

The `is_shared` parameter controls two things in the engine:

1. **k formula** (capacity allocation):
   - `is_shared=False` (GEC): `k = n_tokens / E` - all capacity to routed experts
   - `is_shared=True` (GEC_shared): `k = n_tokens × (G-1) / (G×E)` - reserve capacity for shared expert

2. **Normalization baseline**:
   - `is_shared=False`: `baseline = 0.0` - no implicit weight
   - `is_shared=True`: `baseline = 1.0` - shared expert has implicit weight 1.0

Note: The engine does NOT compute the shared expert itself (that's the wrapper's job). The benchmarks test the engine directly with both `is_shared` modes to verify correct capacity allocation and normalization.

## Scatter Backends

### index_add (Default)
- Uses PyTorch's `index_add_()` for scatter aggregation
- Full topk + threshold support
- Reference implementation

### CSR (Compressed Sparse Row)
- Uses custom Triton kernels (`csr_gather`, `csr_scatter_sum`)
- Token-parallel aggregation
- Validates against index_add backend

## Output Format

Results are grouped by reference implementation with separate performance and validation tables:

**PERFORMANCE:**
- `time (ms)`: Average execution time
- `GB/s`: Memory bandwidth utilization
- `GB moved`: Total data transferred
- `peak (GB)`: Peak memory usage
- `details`: Additional metrics (bytes, etc.)

**VALIDATION:**
- `forward_match`: ✓ if forward output matches reference
- `grad_match`: ✓ if gradients match reference (backward only)
- `max|Δ|`: Maximum absolute difference
- `fwd_max|Δ|`, `bwd_max|Δ|`: Forward/backward specific diffs (backward only)
- `notes`: Diagnostic information for failures

## Directory Structure

```
benchmark/mlp/
├── __main__.py              # Dispatcher
├── forward.py               # Forward benchmarks (topk + threshold)
├── backward.py              # Backward benchmarks (topk + threshold)
├── base.py                  # Base benchmark classes
├── core.py                  # Configuration and utilities
├── common.py                # Result formatting
├── engine_utils.py          # Shared engine utilities (init, warmup, etc.)
├── engine_wrapper.py        # EngineWithScatter composition wrapper
├── flop_counter.py          # FLOP calculations
└── inspect/                 # Profiling tools
    ├── __main__.py
    ├── profile_compiled.py
    └── profile_compiled_autograd.py
```

## Notes

- Benchmarks require CUDA GPU
- CSR backend validates against index_add (reference)
- Numerical tolerance: 1e-4 for forward, 1e-3 for gradients (BF16 precision)
- Threshold mode runs 10 topk warmup iterations to populate cutoff_ema
- Both routing modes support gradients (backward benchmarks)
