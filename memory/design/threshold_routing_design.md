# Threshold Routing Design Decisions

## Overview

Threshold routing is the inference-time variant of GEC routing. This document captures key design decisions and rationale.

## Algorithm Comparison

| Aspect | forward_topk (Training) | forward_threshold (Inference) |
|--------|------------------------|------------------------------|
| **Selection** | Global top-k per expert | Per-token threshold check |
| **Load Balance** | Perfect (exactly k per expert) | Approximate (depends on cutoffs) |
| **Causality** | Non-causal (needs full batch) | Causal (token-by-token) |
| **Backward** | ✅ Supported | ❌ **NOT SUPPORTED** |
| **Performance** | Fast (batched ops) | Slower (for-loop) |
| **Use Case** | Training, batched inference | Autoregressive generation |

## Design Decisions

### 1. Why For-Loop Implementation?

**Alternatives considered:**

1. **Padding** ❌
   - Each expert pads inactive tokens with zeros
   - Wastes compute on masked operations
   - Complex masking logic
   - Poor efficiency with variable load

2. **Sparse Block GEMM** ❌ (not yet available)
   - Ideal future solution
   - Requires specialized kernels not yet implemented
   - Would maintain batched efficiency

3. **For-Loop** ✅ (chosen)
   - Simple and correct
   - No wasted compute
   - Reasonable performance for 4-16 experts
   - Clear path to optimization when sparse kernels available

**Future optimization:** When sparse block GEMM kernels are available, replace for-loop while keeping same API.

**Implementation:**
```python
for expert_idx in range(n_experts):
    # Check threshold per token
    mask = router_logits[:, expert_idx] > self.cutoff_ema[expert_idx]
    active_indices = mask.nonzero().squeeze(-1)

    if len(active_indices) == 0:
        continue

    # Process only active tokens
    x_active = x_flat[active_indices]
    h = self._expert_forward(x_active, expert_idx)

    # Accumulate weighted outputs
    output.index_add_(0, active_indices, h * weights.unsqueeze(-1))
```

### 2. Why Separate Methods?

**Could we unify forward_topk() and forward_threshold()?** No, for several reasons:

**Different algorithms:**
- Topk: Global selection across all tokens (non-causal)
- Threshold: Local per-token decisions (causal)

**Different performance characteristics:**
- Topk: Batched operations, efficient
- Threshold: Sequential operations, slower

**Different use cases:**
- Topk: Training and batched inference
- Threshold: Autoregressive generation

**Code clarity:**
- Clear separation makes bugs easier to find
- Explicit about capabilities (backward support)
- Different optimization strategies

**Dispatcher pattern:**
```python
def forward(self, x, layer_idx=0):
    # Determine effective routing mode
    if self.routing_mode is None:
        # Auto mode: topk for training, threshold for eval
        mode = 'topk' if self.training else 'threshold'
    else:
        # Explicit override
        mode = self.routing_mode

    if mode == 'topk':
        return self.forward_topk(x, layer_idx)
    else:
        return self.forward_threshold(x, layer_idx)
```

**Explicit override**: Models can set `routing_mode='topk'` or `routing_mode='threshold'` to force a specific mode (useful for benchmarking or testing).

### 3. Why No Backward Support?

**Technical reasons:**

1. **For-loop through experts** - inefficient for autograd
   - Each iteration creates separate computation graph
   - Cannot batch gradient computation
   - Poor autograd graph structure

2. **Dynamic masking** - creates ragged computation
   - Variable number of active tokens per expert
   - Difficult to differentiate through index_select
   - Gradient scatter pattern is complex

3. **Index operations** - gradient propagation complexity
   - `index_add_()` gradients require careful handling
   - Mask-based selection complicates backprop
   - Accumulation pattern differs from forward

**Practical reasons:**

Threshold routing is **inference-only**. Training always uses topk for:
- Perfect load balancing (stable training)
- Efficient batched computation
- Clean gradient flow
- Predictable memory usage

**Safety enforcement:**
```python
def forward_threshold(self, x):
    assert not torch.is_grad_enabled(), \
        "Threshold routing does not support backward pass. Use forward_topk() for training."
    # ... threshold routing logic
```

### 4. Normalization Differences

Both topk and threshold normalize by expert count, but with different characteristics:

**Topk (training):**
```python
# Counts known upfront (perfect balance)
counts = n_tokens / n_experts  # Constant per expert
normalizer = counts  # Deterministic
```

**Threshold (inference):**
```python
# Counts computed dynamically
for expert_idx in range(n_experts):
    mask = router_logits[:, expert_idx] > cutoff_ema[expert_idx]
    counts[active_indices] += 1

normalizer = counts.clamp(min=1e-6)  # Variable per token
```

**Key difference:**
- Topk: Same normalization for all selected tokens (expert-wise constant)
- Threshold: Different normalization per token (depends on how many experts selected it)

This ensures consistent output scaling regardless of how many experts contribute to each token.

## Implementation Coverage

**Models with threshold routing:**
- `src/models/gec/reference.py::forward_threshold()`
- `src/models/gec/shared.py::forward_threshold()`
- `src/models/ec.py::forward_threshold()`

**Not implemented (training-only):**
- `src/models/gec/gec.py` - No threshold mode
- `src/models/gec/triton.py` - No threshold mode
- `src/models/gec/triton1.py` - No threshold mode

**Decision:** Threshold implementation prioritized for reference/shared/ec models used in benchmarking. Triton variants can be extended later if inference performance becomes critical.

## Cutoff Initialization for Benchmarking

**Problem:** Fresh models have `cutoff_ema = 0`, making threshold routing degenerate (all logits > 0, massive over-activation).

**Solutions considered:**

1. **Random cutoffs** ✅ (chosen for benchmarks)
   - Initialize: `cutoff_ema.uniform_(0.1, 0.2)`
   - Fast (no warmup needed)
   - Sufficient for performance benchmarking
   - Activation rate similar to trained models

2. **Brief warmup training** (alternative)
   - 50-100 forward passes to populate EMA
   - More realistic activation patterns
   - Slower (adds setup time)

3. **Load checkpoint** (optional)
   - Real trained cutoffs
   - Most realistic behavior
   - Requires checkpoint management

**Benchmark default:** Random cutoffs for speed. Optional `--checkpoint` flag for realistic behavior.

## Training Mode Support

### Dual-Mode Threshold Training

**Challenge**: Threshold routing must support training (with gradients) while maintaining clean cutoff EMA estimates.

**Solution**: Run two passes in parallel during training:
1. **Top-k pass** (torch.no_grad): Extracts cutoffs for EMA updates
2. **Threshold pass** (with gradients): Performs actual routing and computation

**Why dual mode?**
- EMA needs stable topk cutoffs (perfect load balancing)
- Gradients need to flow through threshold routing (actual model behavior)
- Running both ensures EMA quality while training with threshold routing

**Implementation**:
```python
def forward_threshold(self, x, layer_idx=0):
    router_logits = torch.einsum('btc,ce->bte', x, self.router_w)

    # === TRAINING: Dual mode ===
    if self.training:
        with torch.no_grad():
            # Top-k to get cutoffs
            topk_values, _ = torch.topk(router_logits_flat.t(), k=k, dim=1)
            cutoffs = topk_values[:, -1]
            # Update EMA (no gradients)
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs

    # === Threshold routing (supports autograd) ===
    for expert_idx in range(n_experts):
        mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]
        # ... process active tokens (gradients flow here) ...
```

**Performance**: Top-k pass is cheap (no actual expert computation, just sorting). Overhead ~2-5% of forward time.

### Backward Support Difference

| Mode | Backward Support | Why |
|------|------------------|-----|
| **Training threshold** | ✅ Supported (dual-mode) | Gradients flow through threshold routing path |
| **Inference threshold** | ❌ Not supported | For-loop optimization, no need for gradients |

**Classes**:
- Training: `GECMLPTrainableThreshold`, `GECSharedMLPTrainableThreshold`
- Inference: `GECMLP`, `GECSharedMLP` (original classes)

### Two-Stage Training

**Stage 1: EMA calibration (top-k routing)**
- Duration: `step < threshold_warmup_steps` (or full run if `threshold_warmup_steps=-1`)
- Purpose: Build stable cutoff EMA before threshold training/eval reliance
- Routing: Top-k
- EMA: Starts at `ema_start_steps` (no EMA updates before this gate)

**Stage 2: Main training (threshold routing)**
- Duration: `step >= threshold_warmup_steps` (when enabled)
- Purpose: Train with threshold routing behavior
- Routing: Threshold
- EMA: Continues step-boundary updates and is synchronized across GPUs

**Gates in TrainingConfig**:
- `ema_start_steps`: cutoff EMA update start
- `threshold_warmup_steps`: topk→threshold routing switch

For non-threshold-capable model types, both gates are ignored.

## Distributed Training

### Cutoff EMA Synchronization

**Problem**: In DDP training, each GPU computes separate cutoff EMAs that diverge over time.

**Solution**: Synchronize cutoff EMAs across GPUs at every training step boundary.

**Implementation**:
```python
def sync_cutoff_ema(self):
    """Sync cutoff EMA across all GPUs."""
    import torch.distributed as dist
    if not dist.is_initialized():
        return

    for block in self.blocks:
        if hasattr(block.mlp, 'cutoff_ema'):
            dist.all_reduce(block.mlp.cutoff_ema, op=dist.ReduceOp.AVG)
```

### Synchronization Timing

**Where**: After `optimizer.step()`, inside `step_complete()`

**Why this timing**:
- EMA reflects training state that produced the gradients
- Synchronization once per step (efficient)
- All GPUs start next step with identical cutoffs

**Note**: With gradient accumulation, sync happens after all micro-batches complete (see `memory/design/cutoff_accumulation.md` for step-boundary pattern).

**Overhead**: Minimal (~<1ms per step)
- Small tensors (~8-32 floats per layer)
- Single all-reduce per layer
- Overlaps with optimizer step

### Separation of Concerns

**MLP classes**: Implement cutoff accumulation and EMA updates
**BaseGPT**: Coordinates step-boundary operations across layers via `step_complete()`
**Training loop**: Calls `step_complete()` after optimizer.step()

This separation makes the system easier to reason about and extend with future step-boundary operations.

## Configuration Design

### Training Schedule vs Model Architecture

**Key principle**: Threshold routing configuration is a **training schedule decision**, not model architecture.

**Gate locations**:
- `ema_start_steps`: TrainingConfig
- `threshold_warmup_steps`: TrainingConfig
- ✅ **TrainingConfig**: Correct location
- ❌ **ModelConfig**: Wrong, would couple training schedule to model architecture

**Rationale**:
- Same model can be trained with different warmup schedules
- Model checkpoint doesn't depend on training schedule used
- Training config controls when/how training behavior changes
- Model config only describes architecture

**Current implementation note**:
- Routing classes are fixed by `model_type`.
- Training loop controls runtime switching (`set_routing_mode`) and gate-based behavior.

## References

- Paper Algorithm 2 (threshold routing specification)
- `memory/design/notation.md` - GEC formulas and terminology
- `memory/design/cutoff_accumulation.md` - Step-boundary pattern for gradient accumulation
- `src/models/README.md` - Model architecture details
- `benchmark/mlp/README.md` - Benchmarking results
- `memory/archive/completed/threshold_training.md` - Implementation plan
