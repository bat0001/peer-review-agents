# nanochat Training Integration Gaps

**Status**: ✅ IMPLEMENTED - Archived 2025-11-04
**Design Extracted To**:
- `CLAUDE.md` (weight decay philosophy)
- `src/models/README.md` (logits softcapping)
- Weight init pattern already documented in `memory/design/initialization.md`

**Date:** 2025-10-20
**Scope:** Training-related features only (inference deferred)

## Executive Summary

Systematic comparison of `nanochat/nanochat/gpt.py` against `src/models/model_base.py` reveals:
- **1 CRITICAL bug** - Weight initialization never applied
- **3 high-priority training features** - Softcapping, config mismatches

---

## 🚨 CRITICAL: Weight Initialization Bug

### The Problem

Our model trains with **uninitialized weights** due to incorrect initialization flow.

**nanochat pattern (base_train.py:98-100):**
```python
model = GPT(model_config)          # Create model structure
model.to_empty(device="cuda")      # Allocate UNINITIALIZED tensors on GPU
model.init_weights()               # ← Initialize weights AFTER to_empty()
```

**Our broken pattern (train.py:76-78):**
```python
with torch.device("meta"):
    model = BaseGPT(model_config)  # __init__ runs weight init on meta device
model.to_empty(device=device)      # Discards meta weights, creates UNINITIALIZED GPU tensors
# ← MISSING: No init_weights() call!
```

### Why This Happens

`torch.Tensor.to_empty(device)` creates **fresh uninitialized tensors** - it does NOT transfer values from meta device.

Our `BaseGPT.__init__()` calls:
```python
self.apply(self._init_weights_nanochat)  # ← On meta device
self._zero_init_outputs()                # ← On meta device
```

Then `to_empty()` **discards all of this** and creates garbage GPU tensors.

### nanochat's Correct Pattern

**In `__init__` (gpt.py:155-173):**
- Build model structure only
- Create RoPE buffers (fake values ok, will be overwritten)
- Cast wte to bfloat16
- **NO weight initialization**

**In `init_weights()` (gpt.py:175-186):**
- `self.apply(self._init_weights)` - Initialize all modules
- Zero out lm_head.weight and all c_proj weights
- Re-initialize RoPE embeddings (actual device)

### The Fix

**src/models/model_base.py:**
1. Remove `self.apply(self._init_weights_nanochat)` from `__init__`
2. Remove `self._zero_init_outputs()` from `__init__`
3. Add public `init_weights()` method (same as nanochat)
4. Keep helper methods `_init_weights_nanochat()` and `_zero_init_outputs()` for use by `init_weights()`

**train.py:**
```python
with torch.device("meta"):
    model = BaseGPT(model_config)
model.to_empty(device=device)
model.init_weights()  # ← ADD THIS
```

---

## Initialization Details

### Two-Stage Process

Both nanochat and our code use the same logic, we just call it at the wrong time:

**Stage 1: Apply `_init_weights` to all modules**
```python
# From gpt.py:188-199 and our model_base.py:434-446
if isinstance(module, nn.Linear):
    fan_out = module.weight.size(0)
    fan_in = module.weight.size(1)
    std = 1.0 / math.sqrt(fan_in) * min(1.0, math.sqrt(fan_out / fan_in))
    torch.nn.init.normal_(module.weight, mean=0.0, std=std)
elif isinstance(module, nn.Embedding):
    torch.nn.init.normal_(module.weight, mean=0.0, std=1.0)
```

**Stage 2: Zero out output projections (gpt.py:177-182)**
```python
torch.nn.init.zeros_(self.lm_head.weight)
for block in self.transformer.h:
    torch.nn.init.zeros_(block.mlp.c_proj.weight)
    torch.nn.init.zeros_(block.attn.c_proj.weight)
```

**Key detail:** lm_head gets normal init in stage 1, then **explicitly zeroed** in stage 2.

**Critical for Muon:** Zero-init output projections prevent gradient explosion in Muon optimizer.

---

## High-Priority Training Features

### 1. Logits Softcapping

**Status:** Missing
**Impact:** Training stability (Gemma-style)
**Difficulty:** Trivial

**nanochat (gpt.py:278, 283, 290):**
```python
softcap = 15
logits = softcap * torch.tanh(logits / softcap)
```

Applied in `forward()` before computing loss (line 283) and before returning logits (line 290).

**Our code:** No softcapping in `BaseGPT.forward()`

**Fix:** Add to model_base.py line ~523 (after `logits = self.lm_head(x)`):
```python
# Logits softcapping (Gemma-style, nanochat)
softcap = 15.0
logits = softcap * torch.tanh(logits / softcap)
```

---

### 2. Config Mismatches

#### 2a. Vocabulary Size

**nanochat:** `vocab_size: 50304` (padded for GPU efficiency)
**Ours:** `vocab_size: 50257` (GPT-2 standard)

**Rationale:** 50304 = 50257 rounded up to multiple of 64 for better GPU utilization

**Fix:**
- `configs/config.yaml` line 18: change to `vocab_size: 50304`
- Verify tokenizer handles padding correctly

---

#### 2b. Weight Decay

**Status:** Mismatch
**Impact:** Regularization on embeddings/lm_head
**Difficulty:** Trivial

**nanochat:** `weight_decay = 0.0` (base_train.py:42)
**Ours:** `weight_decay = 0.1` (configs/config.yaml:40)

**What is weight decay:**
Weight decay is a regularization technique that penalizes large weights by shrinking them toward zero.

**Mathematical form:**
```
L_total = L_task + (λ/2) * ||θ||²
```

**In AdamW (decoupled weight decay):**
```python
# Each optimizer step:
param = param * (1 - lr * weight_decay) - lr * gradient
         ↑
         Shrink weights by small factor
```

**Applied to:** Only AdamW parameters (wte embeddings + lm_head), NOT Muon matrices.

**Why nanochat uses 0.0:**
1. **Muon has implicit regularization** - Momentum-based optimizer in spectral domain already regularizes
2. **Embeddings are naturally low-rank** - Constrained by vocabulary size, don't need explicit regularization
3. **LMs benefit from memorization** - Unlike image classification, language models should memorize facts; weight decay fights this
4. **Modern training is underparameterized** - These models don't overfit (see scaling laws), no need to regularize

**Our mismatch impact:**
```python
# Every AdamW step with weight_decay=0.1:
wte_weights *= (1 - lr * 0.1)      # Shrinking embeddings!
lm_head_weights *= (1 - lr * 0.1)  # Shrinking output layer!
```

This likely **hurts** performance, especially for rare tokens, and doesn't match nanochat's recipe.

**Fix:** Change `configs/config.yaml` line 40 to `weight_decay: 0.0`

---

#### 2c. Attention Heads

**nanochat GPTConfig (gpt.py:31-33):**
```python
n_head: int = 6          # 6 query heads
n_embd: int = 768
# → head_dim = 128
```

**Our configs:**
| Size | n_head | n_embd | head_dim |
|------|--------|--------|----------|
| tiny | 8 | 512 | 64 |
| small | 12 | 768 | 64 |
| medium | 16 | 1024 | 64 |

**Comparison for 768-dim model:**
- nanochat: **6 heads × 128 dim**
- Our small: **12 heads × 64 dim**

**Design choice:**
- nanochat: Fewer, larger heads (less standard)
- Ours: More, smaller heads (more common in literature)

**Decision needed:** Keep our standard 64-dim heads, or match nanochat's 6-head config?

**Note:** This affects parameter count and compute. For exact replication of nanochat results, should match their config. For best practices, our config may be better.

---

## Already Correct

These nanochat features are **already integrated** and working:

| Feature | Status |
|---------|--------|
| RoPE embeddings | ✓ Functional match |
| Functional RMSNorm (no learnable params) | ✓ Match |
| ReLU² activation | ✓ Match |
| No bias in Linear layers | ✓ Match |
| Untied embeddings (wte ≠ lm_head) | ✓ Match |
| Optimizer setup (AdamW + Muon) | ✓ Equivalent via factory |
| μP LR scaling | ✓ Match |
| Zero-init output projections | ✓ Logic correct (needs init fix) |
| Norm after embedding | ✓ Match |

---

## Summary Table

| Feature | nanochat | Ours | Priority |
|---------|----------|------|----------|
| **Weight init after to_empty()** | ✓ | ✗ | 🚨 CRITICAL |
| **Logits softcapping** | ✓ | ✗ | High |
| **weight_decay** | 0.0 | 0.1 | High |
| **vocab_size** | 50304 | 50257 | Medium |
| **n_head (768d model)** | 6×128d | 12×64d | Medium (design) |

---

## Recommended Action Plan

### Phase 1: Critical Bug Fix (IMMEDIATE)
1. Refactor `BaseGPT.__init__()` to NOT call weight init
2. Add public `init_weights()` method matching nanochat
3. Update `train.py` to call `model.init_weights()` after `to_empty()`
4. Add assertions to verify proper initialization

### Phase 2: Training Features (HIGH PRIORITY)
1. Add logits softcapping to `BaseGPT.forward()` (1-line change)
2. Change weight_decay from 0.1 to 0.0 in config.yaml
3. Update vocab_size to 50304 in config.yaml

### Phase 3: Config Decision (MEDIUM PRIORITY)
Decision needed on n_head:
- **Option A:** Keep our 64-dim heads (more standard, better for ablations)
- **Option B:** Match nanochat's 6 heads × 128d (exact replication)
- **Option C:** Support both via config variants

---

## Files to Modify

**Phase 1 (Critical):**
- `src/models/model_base.py` - Refactor initialization (lines 391-392)
- `train.py` - Add `init_weights()` call (after line 78)

**Phase 2 (High Priority):**
- `src/models/model_base.py` - Add logits softcapping (after line 523)
- `configs/config.yaml` - Update weight_decay (line 40), vocab_size (line 18)

**Phase 3 (Config Decision):**
- `configs/model_size/*.yaml` - Potentially update n_head values

---

## Testing Plan

After Phase 1 fix:
1. Add assertion in `init_weights()` to verify not on meta device
2. Print weight statistics before/after init
3. Verify zero-init outputs (lm_head, c_proj) are actually zeros
4. Run small training run to verify loss goes down

After Phase 2:
1. Verify softcap doesn't break gradients (run backward pass)
2. Compare training curves with/without softcapping
3. Verify vocab_size padding doesn't break tokenizer

---

## References

- nanochat implementation: `nanochat/nanochat/gpt.py`
- nanochat training script: `nanochat/scripts/base_train.py`
- Our base implementation: `src/models/model_base.py`
- Our training script: `train.py`

---

# Detailed Implementation Plan

## Phase 1: Fix Weight Initialization (CRITICAL)

### File: `src/models/model_base.py`

**Step 1.1: Remove initialization from `__init__`**

Current code (lines 391-392):
```python
# Initialize (nanochat style)
self.apply(self._init_weights_nanochat)
self._zero_init_outputs()  # Critical for Muon!
```

**Change to:**
```python
# Note: Initialization moved to init_weights() method
# to be called AFTER to_empty() (see nanochat pattern)
```

**Step 1.2: Add public `init_weights()` method**

Add after `_precompute_rotary_embeddings()` method (around line 471):

```python
def init_weights(self):
    """Initialize model weights (call AFTER to_empty).

    This follows nanochat's pattern:
    1. Create model on meta device
    2. to_empty(device) to allocate uninitialized tensors
    3. init_weights() to actually initialize them

    Critical: Must be called after to_empty(), not in __init__!
    """
    # Verify we're not on meta device
    device = self.wte.weight.device
    assert device.type != 'meta', \
        "init_weights() called on meta device! Call to_empty(device) first."

    # Stage 1: Apply standard initialization to all modules
    self.apply(self._init_weights_nanochat)

    # Stage 2: Zero out output projections (critical for Muon!)
    self._zero_init_outputs()

    # Stage 3: Reinitialize RoPE embeddings on actual device
    head_dim = self.config.n_embd // self.config.n_head
    cos, sin = self._precompute_rotary_embeddings(
        self.rotary_seq_len, head_dim, device=device
    )
    self.cos.copy_(cos)
    self.sin.copy_(sin)

    # Verify zero-init actually worked
    lm_head_norm = self.lm_head.weight.norm().item()
    assert lm_head_norm < 1e-6, \
        f"lm_head should be zero-initialized, got norm={lm_head_norm}"

    print(f"Weights initialized on {device}")
```

**Rationale:**
- Assertion prevents calling on meta device (common mistake)
- Verifies zero-init worked (catches silent failures)
- Prints confirmation for debugging

---

### File: `train.py`

**Step 1.3: Add `init_weights()` call**

Current code (lines 75-78):
```python
# Create model on meta device for faster init (nanochat style)
with torch.device("meta"):
    model = BaseGPT(model_config)
model.to_empty(device=device)
```

**Change to:**
```python
# Create model on meta device for faster init (nanochat style)
with torch.device("meta"):
    model = BaseGPT(model_config)
model.to_empty(device=device)
model.init_weights()  # Initialize AFTER to_empty() (nanochat pattern)
```

**Step 1.4: Add verification**

After initialization, add debug output (lines ~80-85):
```python
model.init_weights()  # Initialize AFTER to_empty() (nanochat pattern)

# Verify initialization (debug mode only)
if not config.training.compile_model:
    with torch.no_grad():
        # Check that weights are initialized (not NaN/Inf)
        for name, param in model.named_parameters():
            assert torch.isfinite(param).all(), \
                f"Parameter {name} contains NaN/Inf after init!"
    print0("✓ Weight initialization verified")
```

---

## Phase 2: Training Features

### File: `src/models/model_base.py`

**Step 2.1: Add logits softcapping**

Current code (around line 522-523):
```python
# Final norm and output projection (nanochat style: functional norm)
x = norm(x)
logits = self.lm_head(x)
```

**Change to:**
```python
# Final norm and output projection (nanochat style: functional norm)
x = norm(x)
logits = self.lm_head(x)

# Logits softcapping (Gemma-style, from nanochat)
softcap = 15.0
logits = softcap * torch.tanh(logits / softcap)
```

**Rationale:**
- Prevents extremely large logits that can cause training instability
- Used in Gemma and nanochat for stability
- Applied before loss computation

---

### File: `configs/config.yaml`

**Step 2.2: Fix weight_decay**

Current code (line 40):
```yaml
weight_decay: 0.1
```

**Change to:**
```yaml
weight_decay: 0.0  # nanochat: no weight decay (Muon has implicit regularization)
```

**Step 2.3: Fix vocab_size**

Current code (line 18):
```yaml
vocab_size: 50257
```

**Change to:**
```yaml
vocab_size: 50304  # Padded to multiple of 64 for GPU efficiency
```

**Rationale:**
- 50304 = 50257 rounded up to multiple of 64
- Better GPU memory alignment
- Matches nanochat

**Step 2.4: Verify tokenizer compatibility**

Check that GPT-2 tokenizer handles 50304 vocab size:
- GPT-2 tokenizer has 50257 tokens
- Indices 50257-50303 will be unused padding tokens
- Should not cause issues as they'll never be predicted/used

---

## Phase 3: Config Decision (n_head)

### Option A: Keep current config (RECOMMENDED)

**Rationale:**
- 64-dim heads are more standard in literature
- Easier to compare with other work
- Our config already working for MoE experiments

**Action:** No changes needed

---

### Option B: Match nanochat exactly

**Changes needed:**

`configs/model_size/small.yaml`:
```yaml
model:
  n_embd: 768
  n_layer: 12
  n_head: 6  # Change from 12 to 6 (nanochat style)
  # head_dim = 128 (768/6)
```

Similar changes for tiny/medium to maintain head_dim ≈ 128.

**Rationale:**
- Exact replication of nanochat results
- Potentially better for fewer, larger heads hypothesis

**Tradeoff:** Different architecture makes comparison harder

---

### Option C: Support both via config variants

Create `configs/model_size/small_nanochat.yaml`:
```yaml
# @package _global_
# GPT-2 Small (nanochat variant): 6 heads × 128 dim

model:
  n_embd: 768
  n_layer: 12
  n_head: 6  # nanochat style: fewer, larger heads
  # head_dim = 128 (768/6)

# Metadata
model_size_name: small_nanochat
```

Usage: `python train.py model_size=small_nanochat`

**Rationale:**
- Best of both worlds
- Easy A/B comparison
- Keeps default as standard config

---

## Verification Checklist

### After Phase 1:
- [ ] Model trains without NaN/Inf
- [ ] Loss decreases consistently
- [ ] lm_head weights are exactly zero at start
- [ ] c_proj weights are exactly zero at start
- [ ] No "uninitialized tensor" warnings
- [ ] Weight statistics look reasonable (mean ≈ 0, std ≈ expected)

### After Phase 2:
- [ ] Logits are bounded to [-15, 15] range
- [ ] Loss computation works correctly
- [ ] Backward pass doesn't explode
- [ ] Vocab size 50304 doesn't break tokenizer
- [ ] Training curves look similar/better

### After Phase 3 (if applied):
- [ ] Parameter count matches expectations
- [ ] Head dimension computed correctly
- [ ] Attention shapes correct in forward pass

---

## Rollback Plan

If issues arise, rollback in reverse order:

**Phase 3 → Phase 2:**
```bash
git checkout configs/model_size/*.yaml
```

**Phase 2 → Phase 1:**
```bash
git checkout configs/config.yaml src/models/model_base.py
# Keep init_weights() changes from Phase 1
```

**Phase 1 → Original (if critical bug):**
```bash
git checkout src/models/model_base.py train.py
```

But Phase 1 MUST be fixed - current code has uninitialized weights!

---

## Implementation Order

1. **Phase 1** - Fix initialization bug FIRST (highest risk)
2. **Test Phase 1** - Small training run (100 steps) to verify
3. **Phase 2** - Add softcapping + config fixes
4. **Test Phase 2** - Compare training curves
5. **Phase 3** - Decision meeting on n_head config

**Total estimated time:** 2-3 hours for implementation + testing
