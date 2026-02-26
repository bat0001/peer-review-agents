# [ARCHIVED] Threshold Routing Implementation Plan

**Completion Date:** 2025-10-06
**Status:** ✅ Completed
**Design decisions extracted to:** `memory/design/threshold_routing_design.md`
**Implementation:**
- `src/models/gec/reference.py::forward_threshold()`
- `src/models/gec/shared.py::forward_threshold()`
- `src/models/ec.py::forward_threshold()`

---

# Threshold Routing Implementation Plan

## Overview

Threshold routing is the **inference-time** variant of GEC routing. Instead of global top-k selection, each token independently activates experts based on learned threshold values (`cutoff_ema`).

## Key Differences: Topk vs Threshold

| Aspect | Topk (Training) | Threshold (Inference) |
|--------|----------------|----------------------|
| **Selection** | Global top-k per expert | Per-token threshold check |
| **Load Balance** | Perfect (exactly k per expert) | Approximate (depends on cutoffs) |
| **Causality** | Non-causal (needs full batch) | Causal (token-by-token) |
| **Backward** | ✅ Supported | ❌ **NOT SUPPORTED** |
| **Use Case** | Training, batched inference | Autoregressive generation |

## Implementation Status

### ✅ Completed

**Models with threshold routing:**
- `src/models/gec/reference.py::forward_threshold()`
- `src/models/gec/shared.py::forward_threshold()`
- `src/models/ec.py::forward_threshold()`

**Core mechanism:**
```python
def forward_threshold(self, x):
    """Causal threshold routing (no backward support)."""
    # Loop through experts
    for expert_idx in range(n_experts):
        # Check threshold per token
        mask = router_logits[:, expert_idx] > self.cutoff_ema[expert_idx]
        active_indices = mask.nonzero().squeeze(-1)

        if len(active_indices) == 0:
            continue

        # Process only active tokens
        x_active = x_flat[active_indices]
        h = self._expert_forward(x_active, expert_idx)
        weights = torch.sigmoid(router_logits[active_indices, expert_idx])

        # Accumulate
        output.index_add_(0, active_indices, h * weights.unsqueeze(-1))
        counts.index_add_(0, active_indices, ones)

    # Normalize by expert count per token
    output = output / counts.clamp(min=1e-6).unsqueeze(-1)
```

### ✅ Backward Pass Assertions (Completed)

**Problem:** If user calls `.backward()` in threshold mode, gradients will be incorrect but PyTorch won't error.

**Solution:** Add assertions to detect and prevent this:

```python
class GECMLPReference(BaseMLP):
    def forward_threshold(self, x):
        # Assert no gradients are being tracked
        assert not torch.is_grad_enabled(), \
            "Threshold routing does not support backward pass. Use forward_topk() for training."

        # ... threshold routing logic
```

**Where added:**
1. ✅ `src/models/gec/reference.py::forward_threshold()` - line 179
2. ✅ `src/models/gec/shared.py::forward_threshold()` - line 236
3. ✅ `src/models/ec.py::forward_threshold()` - line 238

### 🔄 Not Implemented: Other GEC Variants

**Training-only variants (no threshold mode):**
- `src/models/gec/gec.py` - No threshold mode
- `src/models/gec/triton.py` - No threshold mode
- `src/models/gec/triton1.py` - No threshold mode

**Decision:** Threshold implementation prioritized for reference/shared/ec models used in benchmarking.

## Why No Backward?

**Technical reason:** Threshold routing uses:
1. **For-loop through experts** - inefficient for autograd
2. **Dynamic masking** - creates ragged computation
3. **Index operations** - gradient propagation is complex

**Practical reason:** Threshold routing is for **inference only**. Training always uses topk for:
- Perfect load balancing
- Efficient batched computation
- Clean gradient flow

## Testing Strategy

### Topk Benchmarks
```bash
# Test topk (training) path
python -m benchmark.mlp.gec --mode forward --tokens 2048
python -m benchmark.mlp.gec --mode autograd --tokens 2048
```

### Threshold Benchmarks (Implemented)
```bash
# Test threshold (inference) path
python -m benchmark.mlp.gec --mode threshold --tokens 2048

# Compare topk vs threshold
python -m benchmark.mlp.gec --mode comparison --tokens 2048
```

**Requirements for threshold benchmarks:**
1. ✅ Brief training to populate cutoffs (warmup implemented)
2. ✅ Compare forward-only performance (no backward)
3. ✅ Benchmark both modes side-by-side

## Design Rationale

### Why For-Loop?

**Alternatives considered:**
1. ❌ **Padding** - Wastes compute, complex masking
2. ❌ **Sparse block GEMM** - Not available yet (future work)
3. ✅ **For-loop** - Simple, correct, reasonable for 4-16 experts

**Future optimization:** When sparse block GEMM kernels are available, replace for-loop while keeping same API.

### Why Separate Methods?

**Could we unify topk and threshold?** No, because:
- Different selection mechanisms (global vs local)
- Different performance characteristics
- Different use cases (train vs inference)
- Clear separation makes bugs easier to find

### Normalization

Both topk and threshold normalize by expert count:
```python
# Topk: counts known upfront (perfect balance)
counts = n_tokens / n_experts  # Constant

# Threshold: counts computed dynamically
counts = (router_logits > cutoff_ema).sum(dim=0)  # Variable
```

## References

- Paper Algorithm 2 (lines 231-245)
- `memory/design/notation.md` - GEC formulas
- `memory/design/threshold_routing_design.md` - Design decisions (extracted)
- `src/models/README.md` - Model architecture
