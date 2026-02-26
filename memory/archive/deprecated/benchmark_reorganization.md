# Benchmark Reorganization Plan: Engine-Focused, 4-Mode Structure

**Created**: 2025-10-XX
**Status**: DEPRECATED (archived 2025-11-19)
**Goal**: Reorganize benchmarks to focus on ExpertEngine with separate forward/backward × topk/threshold modes

**Why deprecated**: This plan proposed a 4-file structure (forward_topk, forward_threshold, backward_topk, backward_threshold). The actual implementation used a simpler 2-file structure (forward.py, backward.py) with `--routing-mode` flag. See current structure in `benchmark/mlp/README.md`.

## Design Principles

1. **Engine-only benchmarking**: Focus on ExpertEngine and ExpertEngineCSR (the reference implementations)
2. **4 separate files**: forward_topk, forward_threshold, backward_topk, backward_threshold
3. **Engine = reference**: No need for separate reference implementations
4. **CSR = functionally equivalent**: Verify CSR matches dense within tolerance

## New Structure

```
benchmark/mlp/
├── __init__.py                  # Keep
├── __main__.py                  # NEW: Updated dispatcher
├── README.md                    # UPDATE: Document new structure
│
├── base.py                      # Keep (core infrastructure)
├── core.py                      # Keep (config/environment)
├── common.py                    # Keep (formatting)
├── flop_counter.py              # Keep (utilities)
│
├── forward_topk.py              # NEW: ExpertEngine forward (topk routing)
├── forward_threshold.py         # NEW: ExpertEngine forward (threshold routing)
├── backward_topk.py             # NEW: ExpertEngine backward (topk routing)
├── backward_threshold.py        # NEW: ExpertEngine backward (threshold routing)
│
├── archive/                     # NEW: Archive old structure
│   ├── gec/                    # OLD: Move entire gec/ here
│   ├── gec_shared/             # OLD: Move entire gec_shared/ here
│   ├── validation.py           # OLD: Standalone validation
│   ├── timing_utils.py         # OLD: Legacy timing
│   └── benchmark_legacy.py     # OLD: Legacy benchmark
│
└── inspect/                     # UPDATE: Fix imports
    ├── __main__.py             # Update to use new engines
    └── profile_compiled.py     # Update to use new engines
```

## Phase 1: Create New Engine Benchmarks

### File 1: `forward_topk.py` (~200 lines)

**Purpose**: Benchmark ExpertEngine forward pass with top-k routing

**Implementations to test**:
1. **ExpertEngine (is_shared=False)** - GEC configuration
2. **ExpertEngine (is_shared=True)** - GEC_shared configuration (just engine output)
3. **ExpertEngineCSR (is_shared=False)** - CSR backend, GEC config
4. **ExpertEngineCSR (is_shared=True)** - CSR backend, GEC_shared config

**Structure**:
```python
class ExpertEngineForwardTopK(MLPBenchmark):
    """Benchmark ExpertEngine forward pass with top-k routing."""

    def create_implementations(self):
        return {
            'engine-dense-gec': (engine_forward_dense_gec, extras),
            'engine-dense-shared': (engine_forward_dense_shared, extras),
            'engine-csr-gec': (engine_forward_csr_gec, extras),
            'engine-csr-shared': (engine_forward_csr_shared, extras),
        }

    def get_implementation_groups(self):
        # Validate CSR against dense (should be functionally equivalent)
        return {
            'engine-dense-gec': ['engine-csr-gec'],
            'engine-dense-shared': ['engine-csr-shared'],
        }
```

**Key details**:
- All implementations use `model.train()` (topk routing)
- Reference = dense engine (CSR validates against it)
- Measures: latency, memory, FLOPS
- Tests both is_shared=False and is_shared=True

---

### File 2: `forward_threshold.py` (~200 lines)

**Purpose**: Benchmark ExpertEngine forward pass with threshold routing

**Implementations to test**:
1. **ExpertEngine (is_shared=False, threshold)** - GEC threshold mode
2. **ExpertEngine (is_shared=True, threshold)** - GEC_shared threshold mode
3. **ExpertEngineCSR (is_shared=False, threshold)** - CSR threshold (if implemented)
4. **ExpertEngineCSR (is_shared=True, threshold)** - CSR threshold (if implemented)

**Structure**:
```python
class ExpertEngineForwardThreshold(MLPBenchmark):
    """Benchmark ExpertEngine forward pass with threshold routing."""

    def create_implementations(self):
        return {
            'engine-dense-gec-threshold': (engine_forward_threshold_dense_gec, extras),
            'engine-dense-shared-threshold': (engine_forward_threshold_dense_shared, extras),
            # CSR threshold may fall back to topk (per expert_engine_csr.py)
            'engine-csr-gec-threshold': (engine_forward_threshold_csr_gec, extras),
            'engine-csr-shared-threshold': (engine_forward_threshold_csr_shared, extras),
        }

    def setup_threshold_cutoffs(self):
        """Pre-train cutoff EMAs by running topk mode first."""
        # Run 10 topk iterations to populate cutoff_ema
        # Then switch to threshold mode for actual benchmarking
```

**Key details**:
- All implementations use `model.eval()` (threshold routing)
- Need warmup phase to populate cutoff_ema (simulate training)
- May need to wrap in `torch.no_grad()` depending on engine requirements
- CSR engine may fall back to topk if threshold not implemented

---

### File 3: `backward_topk.py` (~250 lines)

**Purpose**: Benchmark ExpertEngine forward+backward with top-k routing

**Implementations to test**:
1. **ExpertEngine (is_shared=False, autograd)** - Full backward pass
2. **ExpertEngine (is_shared=True, autograd)** - Full backward pass
3. **ExpertEngineCSR (is_shared=False, autograd)** - CSR backward
4. **ExpertEngineCSR (is_shared=True, autograd)** - CSR backward

**Structure**:
```python
class ExpertEngineBackwardTopK(MLPAutogradBenchmark):
    """Benchmark ExpertEngine forward+backward with top-k routing."""

    def create_autograd_implementations(self):
        return {
            'engine-dense-gec-autograd': (engine_dense_gec, extras),
            'engine-dense-shared-autograd': (engine_dense_shared, extras),
            'engine-csr-gec-autograd': (engine_csr_gec, extras),
            'engine-csr-shared-autograd': (engine_csr_shared, extras),
        }

    def run_autograd_case(self, impl_name, model, extras):
        # Forward pass
        output, metrics = model.forward_topk(input, layer_idx=0, is_shared=...)

        # Backward pass (compute grad wrt input and all parameters)
        loss = output.sum()
        loss.backward()
```

**Key details**:
- Uses MLPAutogradBenchmark base class
- Returns raw modules (base class handles forward+backward)
- Validates gradients flow correctly
- CSR backward should match dense backward

---

### File 4: `backward_threshold.py` (~250 lines)

**Purpose**: Benchmark ExpertEngine forward+backward with threshold routing

**Implementations to test**:
1. **ExpertEngine (is_shared=False, threshold, autograd)** - Threshold with gradients
2. **ExpertEngine (is_shared=True, threshold, autograd)** - Threshold with gradients
3. **ExpertEngineCSR (threshold, autograd)** - CSR threshold backward (if implemented)

**Structure**:
```python
class ExpertEngineBackwardThreshold(MLPAutogradBenchmark):
    """Benchmark ExpertEngine forward+backward with threshold routing.

    Note: Threshold mode with gradients is used during training when
    threshold_warmup_steps is enabled (dual-path training).
    """

    def setup_threshold_cutoffs(self):
        """Pre-populate cutoff EMAs like forward_threshold.py."""
        # Warmup phase with topk to establish cutoffs

    def create_autograd_implementations(self):
        return {
            'engine-dense-gec-threshold-autograd': (engine_threshold_dense_gec, extras),
            'engine-dense-shared-threshold-autograd': (engine_threshold_dense_shared, extras),
        }
```

**Key details**:
- Threshold mode typically used in eval (no_grad)
- But during training with threshold_warmup, gradients flow through threshold routing
- This tests the dual-path training scenario
- May need special setup to ensure cutoff_ema is populated

---

## Phase 2: Update Entry Point and Dispatcher

### File: `__main__.py` (new dispatcher)

```python
"""Benchmark dispatcher for ExpertEngine.

Usage:
    python -m benchmark.mlp forward_topk       # Forward pass, top-k routing
    python -m benchmark.mlp forward_threshold  # Forward pass, threshold routing
    python -m benchmark.mlp backward_topk      # Forward+backward, top-k routing
    python -m benchmark.mlp backward_threshold # Forward+backward, threshold routing

    # With options
    python -m benchmark.mlp forward_topk --tokens 2048 --hidden 256 --experts 8
"""

import sys
from . import forward_topk, forward_threshold, backward_topk, backward_threshold

MODE_MAP = {
    'forward_topk': forward_topk.main,
    'forward_threshold': forward_threshold.main,
    'backward_topk': backward_topk.main,
    'backward_threshold': backward_threshold.main,
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODE_MAP:
        print("Available modes:", ', '.join(MODE_MAP.keys()))
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    # Remove mode from argv so downstream parsers work
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    MODE_MAP[mode]()

if __name__ == '__main__':
    main()
```

---

## Phase 3: Update Inspection Tools

### File: `inspect/__main__.py`

**Changes**:
- Remove imports: `from src.models.gec import GECMLP, GECMLPReference, ...`
- Add imports: `from src.models.expert_engine import ExpertEngine`
- Update benchmarking logic to use engines directly
- Test both `forward_topk` and `forward_threshold` methods

### File: `inspect/profile_compiled.py`

**Changes**:
- Same import updates as `__main__.py`
- Update model instantiation to create ExpertEngine
- Profile both routing modes

---

## Phase 4: Archive Old Structure

### Move to archive/:
```bash
mv benchmark/mlp/gec/ benchmark/mlp/archive/
mv benchmark/mlp/gec_shared/ benchmark/mlp/archive/
mv benchmark/mlp/validation.py benchmark/mlp/archive/
mv benchmark/mlp/timing_utils.py benchmark/mlp/archive/
mv benchmark/mlp/benchmark_legacy.py benchmark/mlp/archive/
```

### Create `archive/README.md`:
```markdown
# Archived Benchmarks

These benchmarks were archived during the ExpertEngine refactoring (2025-10-XX).

## Why Archived

1. **gec/** and **gec_shared/**: Benchmarked old model structure before ExpertEngine extraction
2. **validation.py**: Standalone script, superseded by new benchmark validation
3. **timing_utils.py**: Legacy timing utilities, unused by current benchmarks
4. **benchmark_legacy.py**: Old benchmark code

## New Structure

Benchmarks now focus on ExpertEngine directly:
- `forward_topk.py` - Forward pass with top-k routing
- `forward_threshold.py` - Forward pass with threshold routing
- `backward_topk.py` - Forward+backward with top-k routing
- `backward_threshold.py` - Forward+backward with threshold routing

See `/benchmark/mlp/README.md` for usage.
```

---

## Phase 5: Update Documentation

### File: `README.md` (update)

**New sections**:

```markdown
# MLP Benchmarking Suite

Benchmarks for ExpertEngine (GEC's routed expert computation core).

## Structure

- **forward_topk.py** - Forward pass benchmarks (top-k routing)
- **forward_threshold.py** - Forward pass benchmarks (threshold routing)
- **backward_topk.py** - Autograd benchmarks (top-k routing)
- **backward_threshold.py** - Autograd benchmarks (threshold routing)

## Usage

```bash
# Forward pass with top-k routing
python -m benchmark.mlp forward_topk --tokens 2048 --hidden 256 --experts 8

# Forward pass with threshold routing (requires warmup)
python -m benchmark.mlp forward_threshold --tokens 2048 --hidden 256 --experts 8

# Autograd with top-k routing
python -m benchmark.mlp backward_topk --tokens 2048 --hidden 256 --experts 8

# Autograd with threshold routing (dual-path training scenario)
python -m benchmark.mlp backward_threshold --tokens 2048 --hidden 256 --experts 8
```

## Implementations Tested

Each benchmark tests:
1. **ExpertEngine (is_shared=False)** - GEC configuration (routed experts only)
2. **ExpertEngine (is_shared=True)** - GEC_shared configuration (with shared expert baseline)
3. **ExpertEngineCSR (is_shared=False)** - CSR aggregation backend (GEC)
4. **ExpertEngineCSR (is_shared=True)** - CSR aggregation backend (GEC_shared)

CSR implementations are validated against dense (index_add) implementations for functional equivalence.

## Validation

- **Reference**: Dense ExpertEngine (index_add aggregation)
- **Validation target**: CSR ExpertEngine (should match dense within tolerance)
- **Tolerance**: 1e-4 for forward pass, 1e-3 for gradients

## Configuration

Benchmarks use `BenchmarkConfig` from `core.py`:
- `num_tokens`: Total tokens (default: 2048)
- `hidden`: Hidden dimension (default: 256)
- `num_experts`: Total experts (default: 8)
- `granularity`: G parameter (default: 2)
- `expansion`: E parameter (default: computed from num_experts)
```

---

## Implementation Details

### Common Patterns Across All 4 Files

**Model instantiation**:
```python
def setup_data(self):
    # Input tensor
    B = self.config.num_tokens // 1024
    T = 1024
    C = self.config.hidden
    self.input_tensor = torch.randn(B, T, C, device=self.device, dtype=torch.bfloat16)

    # Model config
    mc = ModelConfig(
        n_embd=C,
        n_experts=self.config.num_experts,
        granularity=self.config.granularity,
        expansion=self.config.expansion,
        router_activation='sigmoid',
        normalization_mode='fanout',
    )

    # Create engines
    self.engine_dense = ExpertEngine(mc, n_routed_experts=mc.n_experts).to(self.device)
    self.engine_csr = ExpertEngineCSR(mc, n_routed_experts=mc.n_experts).to(self.device)
```

**Runner functions**:
```python
def create_implementations(self):
    def run_dense_gec():
        with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
            output, metrics = self.engine_dense.forward_topk(
                self.input_tensor,
                layer_idx=0,
                is_shared=False
            )
        return output

    def run_csr_gec():
        with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
            output, metrics = self.engine_csr.forward_topk(
                self.input_tensor,
                layer_idx=0,
                is_shared=False
            )
        return output

    return {
        'engine-dense-gec': (run_dense_gec, {'bytes': self.compute_bytes()}),
        'engine-csr-gec': (run_csr_gec, {'bytes': self.compute_bytes()}),
    }
```

**Validation groups**:
```python
def get_implementation_groups(self):
    """CSR should match dense (functionally equivalent)."""
    return {
        'engine-dense-gec': ['engine-csr-gec'],
        'engine-dense-shared': ['engine-csr-shared'],
    }
```

### Threshold-Specific Setup

Both `forward_threshold.py` and `backward_threshold.py` need warmup:

```python
def setup_threshold_cutoffs(self):
    """Populate cutoff EMAs by simulating training with topk."""
    self.engine_dense.train()
    self.engine_csr.train()

    # Run 10 topk iterations to establish cutoffs
    for _ in range(10):
        with torch.no_grad():
            self.engine_dense.forward_topk(self.input_tensor, layer_idx=0, is_shared=False)
            self.engine_csr.forward_topk(self.input_tensor, layer_idx=0, is_shared=False)

    # Finalize EMAs
    self.engine_dense.finalize_cutoff_accumulation()
    self.engine_csr.finalize_cutoff_accumulation()

    # Switch to eval mode for threshold routing
    self.engine_dense.eval()
    self.engine_csr.eval()
```

---

## Benefits of New Structure

### 1. Clarity
- 4 files, each with a single clear purpose
- File names describe exactly what's benchmarked
- No nested subdirectories

### 2. Engine-Focused
- Benchmarks the core computation (ExpertEngine)
- No overhead from thin wrapper classes
- Direct comparison of aggregation backends (dense vs CSR)

### 3. Routing Mode Separation
- Clear distinction between topk and threshold routing
- Each mode has dedicated forward + backward benchmarks
- Easy to see performance differences between routing strategies

### 4. Reduced Code Duplication
- 4 files (~200-250 lines each) vs 14+ files in old structure
- Common patterns extracted to base classes
- No separate "comparison" benchmarks (just run both modes)

### 5. Validation Built-In
- CSR automatically validated against dense
- No need for separate "reference" implementations
- Engine = reference by definition

---

## Testing Strategy

After implementing:

1. **Verify each benchmark runs**:
   ```bash
   python -m benchmark.mlp forward_topk --tokens 1024 --hidden 128 --experts 4
   python -m benchmark.mlp forward_threshold --tokens 1024 --hidden 128 --experts 4
   python -m benchmark.mlp backward_topk --tokens 1024 --hidden 128 --experts 4
   python -m benchmark.mlp backward_threshold --tokens 1024 --hidden 128 --experts 4
   ```

2. **Check validation**:
   - CSR should match dense within tolerance (1e-4 forward, 1e-3 backward)
   - All implementations should pass validation

3. **Performance sanity checks**:
   - Threshold should be faster than topk (less work per token)
   - Backward should be ~2-3x slower than forward
   - CSR and dense should have similar performance (within 20%)

---

## Migration from Old Structure

**Old command**:
```bash
python -m benchmark.mlp.gec forward
python -m benchmark.mlp.gec_shared autograd
```

**New command**:
```bash
python -m benchmark.mlp forward_topk
python -m benchmark.mlp backward_topk
```

**What changed**:
- No more `gec/` vs `gec_shared/` distinction (both tested in same file)
- Explicit routing mode in filename (`_topk`, `_threshold`)
- Explicit operation in filename (`forward_`, `backward_`)

---

## Summary

**Code reduction**: ~14 benchmark files → 4 files
**Lines of code**: ~2000+ lines → ~900 lines (55% reduction)
**Clarity**: Explicit routing modes, engine-focused testing
**Validation**: Built-in CSR vs dense equivalence checking
**Completeness**: All 4 combinations (forward/backward × topk/threshold) covered
