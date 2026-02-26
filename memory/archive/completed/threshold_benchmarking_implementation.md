# [ARCHIVED] Threshold Routing Benchmarking Plan

**Completion Date:** 2025-10-06
**Status:** ✅ Completed
**Results moved to:** `benchmark/mlp/README.md` (Threshold Routing section)
**Implementation:**
- `benchmark/mlp/gec/threshold/` - Threshold-only benchmarks
- `benchmark/mlp/gec/comparison/` - Topk vs threshold comparison

---

# Threshold Routing Benchmarking Plan

## Problem

We have two routing modes:
1. **Topk** - Global top-k selection (training, perfect load balance)
2. **Threshold** - Learned threshold routing (inference, causal)

Current benchmarks only test topk mode. Need to benchmark threshold mode separately.

## Key Challenges

### 1. Threshold Requires Trained Cutoffs

**Problem:** Fresh random models have `cutoff_ema = 0`, which makes threshold routing degenerate.

**Solutions:**

**Option A: Load Pre-trained Checkpoint**
```python
# Load model with learned cutoffs
checkpoint = torch.load('pretrained_gec.pt')
model.load_state_dict(checkpoint)
model.eval()  # Use threshold routing
```

**Option B: Brief Training to Populate Cutoffs** ✅ (Chosen)
```python
# Quick training loop to learn cutoffs
model.train()  # Use topk routing
for i in range(100):  # ~100 steps usually enough
    x = torch.randn(B, T, C)
    output, metrics = model(x)
    # No backward needed, just updating cutoff_ema

# Now use for threshold benchmarking
model.eval()  # Switch to threshold routing
```

**Recommendation:** Start with Option B (brief training) - simpler, no checkpoint management.

### 2. No Backward Pass

**Problem:** Threshold routing only supports forward pass.

**Solution:** Only benchmark forward pass, not autograd.

```python
class ThresholdBenchmark(MLPBenchmark):
    """Benchmark threshold routing (forward-only)."""

    def setup_data(self):
        # ... create models

        # Train briefly to populate cutoff_ema
        self._warmup_cutoffs(num_steps=100)

        # Set to eval mode for threshold routing
        self.model.eval()

    def _warmup_cutoffs(self, num_steps=100):
        """Run brief training to learn cutoff_ema values."""
        self.model.train()
        with torch.no_grad():  # No backward needed
            for _ in range(num_steps):
                x = torch.randn_like(self.input_tensor)
                _, _ = self.model(x)  # Updates cutoff_ema
```

### 3. Comparison with Topk

Want to compare:
- **Topk forward** (training mode, perfect balance)
- **Threshold forward** (inference mode, learned thresholds)

Both forward-only, no backward.

## Implemented Structure

```
benchmark/mlp/gec/
  forward/          # Existing - tests topk
    benchmark.py
  autograd/         # Existing - tests topk
    benchmark.py
  threshold/        # ✅ IMPLEMENTED - tests threshold
    __init__.py
    benchmark.py    # Forward-only threshold benchmark
  comparison/       # ✅ IMPLEMENTED - compare topk vs threshold
    __init__.py
    benchmark.py
```

## Implementation Details

### `benchmark/mlp/gec/threshold/benchmark.py` ✅

```python
"""Threshold routing forward benchmark."""

from benchmark.mlp.base import MLPBenchmark
from src.models.gec import GECMLPReference

class ThresholdForwardBenchmark(MLPBenchmark):
    """Benchmark forward pass with threshold routing (inference mode)."""

    def setup_data(self):
        """Setup models and warm up cutoff_ema."""
        # ... create input and model

        # Warm up cutoff_ema (brief training)
        print(f"Warming up cutoff_ema with {self.warmup_steps} steps...")
        self._warmup_cutoffs(self.gec_reference_mlp, num_steps=self.warmup_steps)

        # Set to eval mode (threshold routing)
        self.gec_reference_mlp.eval()

        print(f"Cutoff EMA values: {self.gec_reference_mlp.cutoff_ema}")

    def _warmup_cutoffs(self, model, num_steps=100):
        """Run brief training to populate cutoff_ema."""
        model.train()  # Use topk routing
        with torch.no_grad():  # No gradients needed
            for _ in range(num_steps):
                x = torch.randn_like(self.input_tensor)
                _, _ = model(x)  # Updates cutoff_ema via EMA

    def create_implementations(self):
        """Create threshold implementations."""
        def gec_reference_threshold():
            with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
                with torch.no_grad():  # Threshold requires no_grad
                    output, _ = self.gec_reference_mlp(self.input_tensor)
                return output

        return {
            'gec-threshold': (
                lambda: None,  # setup
                gec_reference_threshold,
                {'is_reference': True}
            ),
        }
```

### `benchmark/mlp/gec/comparison/benchmark.py` ✅

Compare topk vs threshold in same run:

```python
"""Compare topk vs threshold routing."""

class RoutingComparisonBenchmark(MLPBenchmark):
    """Compare topk (training) vs threshold (inference) routing."""

    def setup_data(self):
        # Create model and warm up cutoffs
        base_model = GECMLPReference(mc).to(self.device)
        self._warmup_cutoffs(base_model)

        # Clone model state for both modes
        self.model_topk = copy.deepcopy(base_model)
        self.model_threshold = copy.deepcopy(base_model)

        self.model_topk.train()  # Use topk routing
        self.model_threshold.eval()  # Use threshold routing

    def create_implementations(self):
        def topk_forward():
            with torch.no_grad():
                output, _ = self.model_topk(self.input_tensor)
            return output

        def threshold_forward():
            with torch.no_grad():
                output, _ = self.model_threshold(self.input_tensor)
            return output

        return {
            'topk': (lambda: None, topk_forward, {'is_reference': True}),
            'threshold': (lambda: None, threshold_forward, {}),
        }
```

## Usage

```bash
# Benchmark threshold routing only
python -m benchmark.mlp.gec --mode threshold \
    --tokens 2048 \
    --hidden 256 \
    --experts 8 \
    --warmup-steps 100 \
    --repeats 50

# Compare topk vs threshold
python -m benchmark.mlp.gec --mode comparison \
    --tokens 2048 \
    --hidden 256 \
    --experts 8 \
    --repeats 50
```

## Expected Results

### Performance Comparison

| Metric | Topk (Training) | Threshold (Inference) |
|--------|----------------|----------------------|
| **Latency** | Faster (batched ops) | Slower (for-loop) |
| **Load Balance** | Perfect | Variable |
| **Memory** | Similar | Similar |
| **Use Case** | Batched inference | Autoregressive gen |

### Validation

**Topk vs Threshold outputs will NOT match** because:
1. Different token selection per expert
2. Different load balancing
3. Different normalization factors

This is expected and correct. They're different algorithms.

## Open Questions → Resolved

1. **How many warmup steps?** ✅ 50-100 steps sufficient (tested)
2. **Should we save/load checkpoints?** ✅ No - brief training is simpler
3. **Benchmark triton variants?** ⏸️ Future work - only after implementing threshold
4. **Test autoregressive generation?** ⏸️ Future work - separate benchmark

## No Backward Assertion

**Important:** Threshold benchmarks must use `torch.no_grad()` or model will assert:

```python
# In forward_threshold():
assert not torch.is_grad_enabled(), \
    "Threshold routing does not support backward pass. Use forward_topk() for training."
```

All threshold benchmark implementations must wrap calls in `with torch.no_grad()`.

## Implementation Status ✅ COMPLETED

1. ✅ Add backward assertions to forward_threshold (done)
2. ✅ Create `benchmark/mlp/gec/threshold/` structure (done)
3. ✅ Implement `ThresholdForwardBenchmark` (done)
4. ✅ Test with `--warmup-steps 50` (done)
5. ✅ Create comparison benchmark (done)
6. ✅ Document results (below)

## Results

**Threshold benchmark:**
```bash
python -m benchmark.mlp.gec --mode threshold --tokens 2048 --hidden 256 --experts 8 --warmup-steps 50
# Cutoff EMA: mean=0.1455, std=0.0073
# Performance: 2.50ms (eager), 3.13ms (compiled)
```

**Comparison benchmark (topk vs threshold):**
```bash
python -m benchmark.mlp.gec --mode comparison --tokens 2048 --hidden 256 --experts 8 --warmup-steps 50
# Topk:      0.77-1.16ms (faster, batched)
# Threshold: 3.57-4.97ms (3-5x slower, for-loop)
```

**Key findings:**
- Threshold routing is ~3-5x slower than topk due to for-loop through experts
- Warmup with 50-100 steps is sufficient to populate cutoff_ema
- Outputs differ (expected) - different token selection algorithms
- Compiled versions don't help much for threshold (limited fusion opportunities)

## References

- `memory/plans/threshold_routing.md` - Threshold implementation details (now archived)
- `memory/design/threshold_routing_design.md` - Design decisions (extracted)
- `benchmark/mlp/README.md` - Usage guide and results
- `benchmark/mlp/gec/forward/benchmark.py` - Existing topk benchmark
- `memory/paper_draft/example_paper.tex` - Algorithm 2 (threshold routing)
