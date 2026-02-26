# Expert Capacity Constraints for Threshold Routing

**Status:** Active (October 2025)
**Related:** `src/models/gec_shared/shared_capacity_threshold.py`

## Motivation

Global Expert Choice (GEC) uses population-level top-k routing during training to achieve perfect load balancing: each expert selects exactly `k = ⌊n_tokens × (G-1) / (G×E)⌋` tokens from the full batch. At inference, we switch to threshold-based routing where each expert activates for tokens with `router_logit >= cutoff_ema`. This creates a **train-test mismatch**:

**Training (top-k):**
- Fixed capacity: exactly k tokens per expert
- Load balanced by construction
- Batch-dependent (requires full batch)

**Inference (threshold):**
- Variable capacity: depends on learned cutoffs and batch composition
- Load balance approximate
- Causal (token-by-token decisions)

This mismatch can cause two problems:

1. **Underutilization**: Too few tokens exceed threshold → experts idle → wasted computation
2. **Overload**: Too many tokens exceed threshold → memory bottlenecks → inconsistent scaling

## Solution: Capacity-Bounded Threshold Routing

During training with threshold routing, we enforce **hard capacity bounds** on expert usage:

```
k_target = ⌊n_tokens × (G-1) / (G×E)⌋
k_min = int(k_target × (1 - α))
k_max = int(k_target × (1 + α))
```

Where `α ∈ [0,1]` is the capacity factor (typically 0.2 for ±20% bounds).

For each expert:
1. Count tokens above threshold: `n_above = (router_logits >= cutoff_ema).sum()`
2. Apply capacity bounds:
   - If `n_above > k_max`: **Clip** to top k_max tokens by router logit
   - If `n_above < k_min`: **Expand** to top k_min tokens (relax threshold)
   - Otherwise: Use all tokens above threshold (pure threshold)

This ensures each expert processes a consistent number of tokens while still respecting learned thresholds when possible.

## Design Decisions

### 1. Capacity Only During Training

**Rationale:** Capacity constraints are a training stabilization mechanism. At inference, the learned cutoffs should naturally produce balanced loads if training was successful.

**Implementation:**
- Training: `capacity_enabled = (expert_capacity_factor >= 0) and self.training`
- Inference: Pure threshold routing (Algorithm 2 from paper), no bounds

### 2. Sentinel Value: -1 for Disabled

**Rationale:** Using `-1` as "disabled" is safer than `None` for arithmetic operations (no type errors).

**Implementation:**
```python
if self.config.expert_capacity_factor >= 0 and self.training:
    # Apply capacity bounds
else:
    # Pure threshold routing
```

### 3. Dual-Path Training

**Rationale:** We still need EMA cutoff updates from clean top-k selection, while using capacity-bounded threshold for the actual computation path.

**Implementation:**
```python
# Path 1: Top-k (no_grad) for EMA
with torch.no_grad():
    topk_indices = torch.topk(router_logits[:, i], k=k_target)
    cutoff = topk_indices[-1]
    cutoff_ema = β × cutoff_ema + (1-β) × cutoff

# Path 2: Capacity-bounded threshold (with grad) for computation
n_above = (router_logits[:, i] >= cutoff_ema).sum()
if n_above > k_max:
    active_indices = torch.topk(router_logits[:, i], k=k_max)
elif n_above < k_min:
    active_indices = torch.topk(router_logits[:, i], k=k_min)
else:
    active_indices = (router_logits[:, i] >= cutoff_ema).nonzero()
```

### 4. Clip vs Expand Logic

**Overflow (n_above > k_max):**
- Problem: Threshold too low, too many tokens selected
- Solution: Clip to top k_max by router logit
- Effect: Discards lowest-scoring tokens, tightens threshold implicitly

**Underflow (n_above < k_min):**
- Problem: Threshold too high, too few tokens selected
- Solution: Expand to top k_min tokens
- Effect: Includes below-threshold tokens, relaxes threshold implicitly

This creates implicit feedback: if thresholds are miscalibrated, capacity bounds push expert usage toward the target range.

## New Metrics

When capacity is enabled (`expert_capacity_factor >= 0`), we track:

### Global Metrics

- **`capacity_hit_rate`**: `(overflow + underflow) / n_experts`
  - Fraction of experts hitting either bound
  - High value → thresholds poorly calibrated

- **`capacity_overflow_rate`**: `overflow / n_experts`
  - Fraction hitting k_max (threshold too low)

- **`capacity_underflow_rate`**: `underflow / n_experts`
  - Fraction hitting k_min (threshold too high)

- **`raw_mean`**: `mean(n_above_per_expert)`
  - Average tokens per expert that pure threshold would select
  - Compare with k_target to assess calibration

- **`raw_std`**: `std(n_above_per_expert)`
  - Variance in pure threshold selection
  - Lower is better (more consistent across experts)

### Per-Expert Metrics (Representative Layers)

- **`repr_L{i}_capacity_status`**: Tensor of shape (n_routed_experts,)
  - Values: 0 (hit k_min), 1 (within bounds), 2 (hit k_max)
  - Identifies which experts struggle with threshold calibration

- **`repr_L{i}_actual_k`**: Tensor of shape (n_routed_experts,)
  - Actual number of tokens selected after capacity enforcement
  - Should be in [k_min, k_max] by construction

- **`repr_L{i}_raw_k`**: Tensor of shape (n_routed_experts,)
  - Tokens pure threshold would select (n_above)
  - Compare with actual_k to see capacity impact

## Configuration

### Model Config

In `src/models/model_base.py:62`:
```python
expert_capacity_factor: float = -1.0  # -1 = disabled, ≥0 = enabled
```

### YAML Config

In `configs/mlp/gec_shared_capacity.yaml`:
```yaml
model:
  model_type: gec_shared_capacity
  expert_capacity_factor: 0.2  # ±20% bounds
```

### Training Script

In `script/run_gec_shared_2stage.sh`:
```bash
EXPERT_CAPACITY_FACTOR=0.2  # Enable capacity
# or
EXPERT_CAPACITY_FACTOR=-1   # Disable (pure threshold)
```

## Usage Examples

### With Capacity (Standard)

```bash
python train.py \
  mlp=gec_shared_capacity \
  training.ema_start_steps=200 \
  training.threshold_warmup_steps=1000 \
  model.expert_capacity_factor=0.2
```

Behavior:
- Steps 0-199: Top-k routing, EMA not yet updating
- Steps 200-999: Top-k routing, EMA updating
- Steps 1000+: Capacity-bounded threshold routing
  - Each expert processes k ∈ [k×0.8, k×1.2] tokens
  - Tracks capacity hit rates and raw vs actual selection

### Without Capacity (Pure Threshold)

```bash
python train.py \
  mlp=gec_shared_capacity \
  training.ema_start_steps=200 \
  training.threshold_warmup_steps=1000 \
  model.expert_capacity_factor=-1
```

Behavior:
- Steps 0-199: Top-k routing, EMA not yet updating
- Steps 200-999: Top-k routing, EMA updating
- Steps 1000+: Pure threshold routing
  - No capacity bounds, uses all tokens above cutoff_ema
  - No capacity metrics tracked

### Comparison Baseline

For ablation studies, compare:

1. **`gec_shared`** - Standard GEC shared (top-k only)
2. **`gec_shared_capacity` with `α=-1`** - Pure threshold
3. **`gec_shared_capacity` with `α=0.2`** - Capacity-bounded threshold

This isolates the impact of capacity constraints from trainable threshold routing.

## Implementation Files

### Core Module
- **`src/models/gec_shared/shared_capacity_threshold.py`**
  - `GECSharedMLPCapacityThreshold` class
  - Inherits from `GECSharedMLP`
  - Overrides `forward()` and `forward_threshold()` with capacity logic

### Model Loading
- **`src/models/model_base.py:442-444`**
  - Maps `model_type='gec_shared_capacity'` to class
  - Validates model type in config

### Configuration
- **`configs/mlp/gec_shared_capacity.yaml`**
  - Default capacity factor: 0.2
  - Documents -1 for disabled

### Training Script
- **`script/run_gec_shared_2stage.sh`**
  - Passes `model.expert_capacity_factor` from env var
  - Displays capacity bounds in output

## Research Questions

1. **Does capacity improve training stability?**
   - Compare loss curves and gradient norms with/without capacity
   - Check if capacity reduces variance in expert usage

2. **Does capacity reduce train-test mismatch?**
   - Compare eval perplexity at end of training
   - Check if raw_k converges closer to k_target with capacity

3. **What is the optimal capacity factor?**
   - Ablate α ∈ {0.1, 0.2, 0.3} to find best trade-off
   - Higher α = more tolerance, lower α = stricter bounds

4. **How often do capacity bounds activate?**
   - Track `capacity_hit_rate` over training
   - Early training: expect high hit rate (miscalibrated thresholds)
   - Late training: expect low hit rate (well-calibrated thresholds)

## Related Documentation

- **Paper Section**: Section 3.3 "Expert Capacity Constraints"
- **Algorithm**: Algorithm 3 in paper
- **Model README**: `src/models/README.md` (Trainable Threshold Routing section)
- **Config README**: `configs/README.md` (mlp/ section)
- **CLAUDE.md**: Brief mention of capacity as optional feature
