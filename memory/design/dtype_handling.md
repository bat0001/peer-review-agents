# Dtype Handling in Mixed Precision Training

**Date:** 2025-10-18
**Context:** Autocast conversion in benchmarks revealed dtype promotion bugs in GEC models

---

## Background

PyTorch's `torch.autocast` enables mixed precision training by automatically converting eligible operations to BF16 for faster computation with minimal accuracy loss.

### Autocast Behavior

Under `torch.autocast(device_type='cuda', dtype=torch.bfloat16)`:

**What stays FP32:**
- Model parameters (weights, biases)
- Operations not in the autocast whitelist

**What becomes BF16:**
- Matrix multiplications (`torch.matmul`, `torch.bmm`, `F.linear`)
- Convolutions
- Other whitelisted operations

**Promotion rules:**
- Element-wise operations between different dtypes promote to higher precision
- Example: `tensor_bf16 + tensor_fp32` → `tensor_fp32`

---

## Expected Dtype Flow in GEC Models

### Ideal Flow (what we want)

```
Input (BF16 from previous layer)
  ↓
torch.bmm(x_bf16, weight_fp32) → h_bf16
  ↓
h_bf16 + bias_fp32 → ??? (THIS IS THE PROBLEM)
  ↓
Output (should be BF16)
```

### What Actually Happens

```python
h = torch.bmm(x_permuted, self.weight1.transpose(1, 2))  # BF16 (autocasted)
h = h + self.bias1.unsqueeze(1)                          # FP32 (promoted!)
h = self.act(h)                                          # FP32
h = torch.bmm(h, self.weight2.transpose(1, 2))          # BF16 (autocasted)
h = h + self.bias2.unsqueeze(1)                          # FP32 (promoted!)
```

**Result:** Intermediate `h` oscillates between BF16 and FP32, ending in FP32.

---

## The Bug

### Symptom
```
RuntimeError: index_add_(): self (BFloat16) and source (Float) must have the same scalar type
```

### Root Cause

**In AddIntoSharedGECMLP:**
```python
shared_output = F.linear(...)  # BF16 under autocast
h = ... computation ...         # Ends up as FP32 due to bias promotion
shared_output.index_add_(0, indices, h)  # ERROR: BF16 buffer + FP32 source
```

**In baseline GECSharedMLP:**
```python
routed_output = torch.zeros_like(x_flat)  # FP32 (x_flat is FP32 input)
routed_output.index_add_(0, indices, h)   # FP32 + FP32 → no error
output = shared_output_bf16 + routed_output_fp32  # Promotes to FP32!
```

**Baseline was returning FP32 instead of BF16**, defeating the purpose of mixed precision!

---

## Why This Happens: F.linear vs Manual BMM

### DenseMLP (works correctly)

```python
h = F.linear(x, weight, bias)  # Returns BF16 under autocast
```

`F.linear` handles bias addition internally in a way that maintains BF16.

### GEC Models (needs manual handling)

```python
h = torch.bmm(x_batched, weight_batched)  # BF16
h = h + bias_batched                       # FP32 (promotion!)
```

**Why can't we use F.linear?**
- GEC has batched expert weights: `(n_experts, expert_dim, hidden_dim)`
- Each expert has different weights
- `F.linear` expects a single weight matrix
- We need `torch.bmm` for parallel expert computation

---

## The Fix

### Approach: Cast Only at Dtype Boundaries

Instead of fighting dtype promotion, embrace FP32 intermediate computation and cast only when necessary.

**Before (broken):**
```python
weights = self.apply_router_activation(topk_values, ...).view(...)
weights = weights.to(h.dtype)  # Trying to force dtype matching

normalizer_h = normalizer[...].view(...).to(h.dtype)  # More forced casting
h = h * weights / normalizer_h

shared_output.index_add_(0, indices, h)  # Still fails!
```

**After (fixed):**
```python
weights = self.apply_router_activation(topk_values, ...).view(...)
# Let weights stay in their natural dtype (BF16)

normalizer_h = normalizer[...].view(...)
# Let normalizer_h stay in its natural dtype (FP32)

h = h * weights / normalizer_h
# Let FP32 computation happen (higher precision)

# Cast ONLY at the boundary where dtype must match
shared_output.index_add_(0, indices, h.to(shared_output.dtype))
```

### Changes Made

**1. AddIntoSharedGECMLP (`add_into_shared.py`):**
- Removed: `weights.to(h.dtype)`
- Removed: `normalizer_h.to(h.dtype)`
- Added: `h.to(shared_output.dtype)` at `index_add_`

**2. GECSharedMLPReference (`shared.py`):**
- Removed: `normalizer_h.to(h.dtype)`
- Changed: `routed_output = torch.zeros_like(shared_output)` (was `zeros_like(x_flat)`)
- Added: `h.to(routed_output.dtype)` at `index_add_`

### Why This Works

1. **Simpler code**: Fewer explicit dtype casts
2. **Higher precision**: Intermediate math in FP32 is more accurate
3. **Correct output**: Final output is BF16 (matches autocast intent)
4. **Compiler friendly**: torch.compile can fuse FP32 operations
5. **Single cast point**: Only cast where dtype boundaries require it

---

## Benchmark Implications

### Input Dtype Matters

**First layer in model:**
```
Embeddings (FP32) → Attention/MLP (receives FP32 input)
```

**Intermediate layers:**
```
Previous layer output (BF16) → Attention/MLP (receives BF16 input)
```

### Benchmark Setup

**MLPs are intermediate layers** → benchmarks must use BF16 inputs:

```python
# WRONG (old approach):
self.input_tensor = torch.randn(B, T, C, device=device)  # FP32

# RIGHT (fixed):
self.input_tensor = torch.randn(B, T, C, device=device, dtype=torch.bfloat16)
```

**Why BF16 inputs:**
- Matches real training behavior for intermediate layers
- Tests the actual dtype flow models experience
- Exposes dtype bugs that FP32 inputs would mask

---

## Testing Results

### Before Fix
- Baseline GECSharedMLP: Output FP32 under autocast ❌
- AddIntoSharedGECMLP: Crashed with dtype mismatch ❌
- Benchmarks: Used FP32 inputs, forcing everything to BF16 to avoid crashes

### After Fix
- Baseline GECSharedMLP: Output BF16 under autocast ✅
- AddIntoSharedGECMLP: Works correctly, output BF16 ✅
- Benchmarks: Use BF16 inputs, all validation checks pass ✅

**Validation errors:** < 1e-03 (acceptable for BF16 precision)

---

## Key Takeaways

1. **Autocast doesn't prevent dtype promotion** - element-wise ops still follow standard rules
2. **F.linear handles bias correctly** - but batched ops need manual handling
3. **Don't fight FP32 promotion** - cast only at boundaries
4. **Benchmarks must match training** - use BF16 inputs for intermediate layers
5. **Final output dtype matters** - must be BF16 to avoid promoting entire forward pass

---

## Accumulation Precision in Scatter Operations

**Date:** 2025-12-03
**Context:** Benchmark validation showed ~6e-2 max|Δ| between torch reference and Triton kernels

### The Problem

PyTorch's `index_add_` accumulates in the **output tensor's dtype**:
```python
out = torch.zeros(N, H, dtype=torch.bfloat16)
out.index_add_(0, indices, source)  # BF16 accumulation
```

Our Triton kernels accumulate in **FP32** for numerical stability:
```python
# In Triton kernel (src/kernels/csr.py:180-212)
acc = tl.zeros([BLOCK_X], dtype=tl.float32)  # FP32 accumulator
x = tl.load(expert_ptr, ...).to(tl.float32)
w = tl.load(weights + lin).to(tl.float32)
acc += x * w
tl.store(out_ptr, acc.to(token_out.dtype.element_ty), ...)  # Downcast to BF16
```

This mismatch caused validation failures (~3-6e-2 difference).

### Reference Library Survey

| Library | Router Weights | Gate Values | Accumulation |
|---------|---------------|-------------|--------------|
| **ScatterMoE** | Model dtype (BF16) | FP32 softmax → cast back | Model dtype |
| **MegaBlocks** | Model dtype | Model dtype | **FP32 in Triton kernel** |
| **MoE++** | FP32 (explicit) | FP32 | Model dtype (index_add_) |

**MegaBlocks pattern** (what we follow):
- Weights stored in BF16 (memory efficient)
- Kernel loads BF16, converts to FP32 for computation
- Stores result back to BF16

### Our Design Decision

**Follow MegaBlocks**: BF16 storage, FP32 kernel accumulation, BF16 output.

```
BF16 expert_out → load → FP32
FP32 weights    → load → FP32
                    ↓
              FP32 accumulation
                    ↓
              store → BF16 output
```

**Rationale:**
1. Memory efficient (BF16 storage)
2. Numerically stable (FP32 accumulation avoids precision loss when summing many small values)
3. Consistent output dtype (BF16 for downstream layers)

### Benchmark Setup

Two baselines to compare both behaviors:

| Baseline | Accumulation | Purpose |
|----------|--------------|---------|
| `torch` | FP32 | Reference for Triton kernels (validation) |
| `torch-bf16` | BF16 | Shows PyTorch native behavior |

```python
# torch (FP32 accumulation - matches Triton)
out = self.shared_out.float()
weighted = self.expert_out_flat.float() * self.weights_flat_fp32
out.index_add_(0, self.indices, weighted)
return out.to(torch.bfloat16)

# torch-bf16 (native BF16 accumulation)
out = self.shared_out.clone()
weighted = torch.mul(self.expert_out_flat, self.weights_flat_fp32)
out.index_add_(0, self.indices, weighted.to(out.dtype))
return out
```

### Expected Validation Results

| Comparison | Expected max|Δ| |
|------------|---------------|
| `torch` vs Triton kernels | ~1e-3 (FP32 rounding) |
| `torch-bf16` vs `torch` | ~3-6e-2 (BF16 vs FP32 accumulation) |

### Interesting Observation: torch.compile Performance

After compilation, FP32 accumulation can be **faster** than BF16:

```
torch (FP32):    4.5ms → 178 GB/s
torch-bf16:      7.2ms → 111 GB/s
```

Hypothesis: torch.compile fuses the FP32 path better because it's a cleaner linear chain without intermediate dtype casts in the hot path.

---

## References

- PyTorch Autocast docs: https://pytorch.org/docs/stable/amp.html
- Related plan: `memory/plans/benchmark_autocast_plan.md`
- Implementation: `src/models/gec_shared/shared.py`, `add_into_shared.py`
- Scatter benchmarks: `benchmark/permutation/scatter*/benchmark.py`
