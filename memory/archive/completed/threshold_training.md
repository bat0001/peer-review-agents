# Threshold Training Mode Implementation Plan

**Status**: ✅ IMPLEMENTED - Archived 2025-11-04
**Design Extracted To**:
- `memory/design/threshold_routing_design.md` (dual-mode training, distributed training, config design)
- `src/models/README.md` (routing mode API)
- `configs/README.md` (config organization principle)

**Date**: 2025-10-27

## Goal

Enable threshold-based routing during training with cutoff EMA tracking, supporting distributed training.

## Design Overview

### Two-Stage Training
1. **Stage 1 (warmup)**: Top-k routing to build stable cutoff EMA
2. **Stage 2 (main)**: Threshold routing with parallel top-k for continued EMA updates (dual mode)

### Key Requirements
- Threshold routing must support gradients (for training)
- Cutoff EMA synchronized across GPUs every step
- No expert capacity limits (using for-loop, so no OOM risk)
- Backward compatible with existing inference threshold mode

---

## Architecture Decisions

### 1. Class Hierarchy: Inheritance Pattern

**Decision**: Create new classes inheriting from existing GEC/GEC_shared
- `GECMLPTrainableThreshold` inherits from `GECMLP`
- `GECSharedMLPTrainableThreshold` inherits from `GECSharedMLP`

**Why inheritance?**
- Keep original classes unchanged (backward compatibility)
- Easy to test and compare implementations
- Clean separation of concerns (training vs inference)
- Can easily rollback if issues arise

**Files**:
- `src/models/gec/gec_trainable_threshold.py` (new)
- `src/models/gec_shared/shared_trainable_threshold.py` (new)

### 2. Configuration Design

**TrainingConfig only** (no ModelConfig changes):
```python
@dataclass
class TrainingConfig:
    threshold_warmup_steps: int = 0  # 0 = disabled, >0 = switch at step N
```

**Rationale**:
- Threshold training is a **training schedule decision**, not model architecture
- Same model can be trained with/without threshold warmup
- Simpler: just one config parameter

**Alternative considered**: `threshold_warmup_steps = -1` to indicate disabled
- **Rejected**: `0` is more Pythonic (falsy = disabled)
- Using `> 0` check is cleaner than `!= -1`

**Model class selection**:
- Check `threshold_warmup_steps > 0` in `_get_mlp_class()`
- Automatically use trainable variant if warmup enabled
- No explicit `use_trainable_threshold` flag needed

### 3. Dual-Mode Threshold Routing

**Implementation**: Modify `forward_threshold()` in new classes

```python
def forward_threshold(self, x, layer_idx=0):
    """Threshold routing supporting training and inference.

    Training mode (dual mode):
      1. Parallel top-k (torch.no_grad) for EMA updates
      2. Threshold routing (with gradients) for actual computation

    Eval mode (inference):
      - Threshold routing only (no top-k overhead)
    """
    # Compute router logits (shared)
    router_logits = torch.einsum('btc,ce->bte', x, self.router_w)

    # === TRAINING: Dual mode ===
    if self.training:
        with torch.no_grad():
            # Top-k to get cutoffs
            topk_values, _ = torch.topk(router_logits_flat.t(), k=k, dim=1)
            cutoffs = topk_values[:, -1]
            # Update EMA
            self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs

    # === Threshold routing (supports autograd) ===
    for expert_idx in range(n_experts):
        mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]
        # ... process active tokens (gradients flow here in training) ...
```

**Key changes from original**:
1. Remove `assert not torch.is_grad_enabled()`
2. Add dual-mode logic in training
3. Keep inference path unchanged

### 4. Distributed Cutoff EMA Sync

**Strategy**: All-reduce after backward, before optimizer step

**Implementation**:
```python
# BaseGPT.sync_cutoff_ema()
def sync_cutoff_ema(self):
    for block in self.blocks:
        if hasattr(block.mlp, 'cutoff_ema'):
            dist.all_reduce(block.mlp.cutoff_ema, op=dist.ReduceOp.AVG)
```

**Timing**: After gradient accumulation, before optimizer
- EMA updates happen during forward pass
- Sync before optimizer ensures consistent cutoffs for next forward
- Matches gradient sync timing

**Overhead**: Minimal (~<1ms)
- Small tensors (~8-32 floats per layer)
- Single all-reduce per layer

---

## Implementation Plan

### Phase 1: Core Implementation

1. **Add config field**
   - File: `src/config.py`
   - Add: `TrainingConfig.threshold_warmup_steps: int = 0`

2. **Create GECMLPTrainableThreshold**
   - File: `src/models/gec/gec_trainable_threshold.py` (new)
   - Inherit from `GECMLP`
   - Override `forward_threshold()` with dual-mode support
   - Update: `src/models/gec/__init__.py`

3. **Create GECSharedMLPTrainableThreshold**
   - File: `src/models/gec_shared/shared_trainable_threshold.py` (new)
   - Inherit from `GECSharedMLP`
   - Override `forward_threshold()` with dual-mode support
   - Update: `src/models/gec_shared/__init__.py`

4. **Update BaseGPT**
   - File: `src/models/model_base.py`
   - Add: `sync_cutoff_ema()` method
   - Add: `set_routing_mode()` method
   - Update: `_get_mlp_class()` to select trainable variant

### Phase 2: Training Loop Integration

5. **Integrate training loop**
   - File: `train.py`
   - Before loop: Set initial routing mode if warmup enabled
   - Inside loop: Switch to threshold at warmup step
   - After backward: Call `sync_cutoff_ema()` if in threshold mode

### Phase 3: Testing & Validation

6. **Create experiment config**
   - File: `configs/experiment/threshold_training.yaml`
   - Test with small model, short run

7. **Test suite**
   - Single GPU training
   - Multi-GPU training (verify EMA sync)
   - Gradient flow verification
   - Loss curve comparison (top-k vs threshold)

8. **Update benchmarks** (optional)
   - Make threshold benchmarks compatible with training mode
   - Add dual-mode performance benchmarks

### Phase 4: Documentation

9. **Design documentation**
   - Move this plan to `memory/design/threshold_training.md`
   - Extract design decisions and rationale

10. **Update module READMEs**
    - `src/models/README.md`: Add threshold training mode section
    - `configs/README.md`: Document threshold_warmup_steps usage

---

## Implementation Details

### Code Changes

#### 1. TrainingConfig (src/config.py)

```python
@dataclass
class TrainingConfig:
    # ... existing fields ...

    # Threshold training
    threshold_warmup_steps: int = 0  # 0 = disabled, >0 = switch at step N
```

#### 2. GECMLPTrainableThreshold (src/models/gec/gec_trainable_threshold.py)

```python
from typing import Dict, Tuple
import torch
from torch import Tensor
from .gec import GECMLP


class GECMLPTrainableThreshold(GECMLP):
    """GEC with threshold routing that supports training mode.

    Extends GECMLP with training-compatible threshold routing:
    - Training mode: Dual-path (top-k for EMA + threshold for routing)
    - Eval mode: Threshold only (same as inference)

    Backward compatible with parent GECMLP for top-k routing.
    """

    def forward_threshold(self, x: Tensor, layer_idx: int = 0) -> Tuple[Tensor, Dict[str, Tensor]]:
        """Threshold routing supporting both training and inference.

        Training mode (dual mode):
          1. Top-k (no_grad) to extract cutoffs for EMA updates
          2. Threshold routing (with gradients) for actual computation

        Eval mode:
          - Threshold routing only (no top-k overhead)
        """
        B, T, C = x.shape
        n_experts = self.router_w.shape[1]

        # Compute router logits
        router_logits = torch.einsum('btc,ce->bte', x, self.router_w)
        router_logits_flat = router_logits.view(-1, n_experts)
        n_tokens = B * T
        x_flat = x.view(-1, C)

        # === TRAINING: Parallel top-k for EMA ===
        if self.training:
            with torch.no_grad():
                k = n_tokens // self.config.expansion
                topk_values, _ = torch.topk(
                    router_logits_flat.t(), k=min(k, n_tokens), dim=1
                )
                cutoffs = topk_values[:, -1] if k > 0 else torch.zeros(n_experts, device=x.device)

                # Update EMA
                self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs

        # === THRESHOLD ROUTING (supports autograd) ===
        # (Rest same as parent's forward_threshold, but without gradient assertion)
        all_active_indices = []
        all_weights = []
        all_expert_outputs = []

        for expert_idx in range(n_experts):
            mask = router_logits_flat[:, expert_idx] > self.cutoff_ema[expert_idx]
            active_indices = mask.nonzero(as_tuple=False).squeeze(-1)

            if len(active_indices) == 0:
                continue

            # Process active tokens
            x_active = x_flat[active_indices]
            h = torch.bmm(
                x_active.unsqueeze(0),
                self.weight1[expert_idx].unsqueeze(0).transpose(1, 2)
            ).squeeze(0)
            h = torch.relu(h).square()
            h = torch.bmm(
                h.unsqueeze(0),
                self.weight2[expert_idx].unsqueeze(0).transpose(1, 2)
            ).squeeze(0)

            # Router activation
            weights = self.apply_router_activation(
                router_logits_flat[active_indices, expert_idx],
                self.config.router_activation
            )

            all_active_indices.append(active_indices)
            all_weights.append(weights)
            all_expert_outputs.append(h)

        # Combine outputs
        if len(all_active_indices) > 0:
            permutation_indices = torch.cat(all_active_indices)
            weights = torch.cat(all_weights)
            expert_outputs = torch.cat(all_expert_outputs)

            # Compute normalizer
            normalizer = self.compute_normalizer(
                mode=self.config.normalization_mode,
                n_tokens=n_tokens,
                indices=permutation_indices,
                weights=weights,
                router_logits_flat=router_logits_flat,
                router_activation=self.config.router_activation,
                device=x.device
            )

            # Normalize and scatter
            normalizer_h = normalizer[permutation_indices].unsqueeze(-1).to(expert_outputs.dtype)
            h_weighted = expert_outputs * weights.unsqueeze(-1) / normalizer_h

            output = torch.zeros_like(x_flat)
            output.index_add_(0, permutation_indices, h_weighted.to(output.dtype))
        else:
            output = torch.zeros_like(x_flat)
            permutation_indices = torch.tensor([], dtype=torch.long, device=x.device)

        output = output.view(B, T, C)

        # Metrics (simplified for now)
        metrics = {
            'gec_cutoff_ema': self.cutoff_ema.clone(),
        }

        return output, metrics
```

#### 3. GECSharedMLPTrainableThreshold (similar pattern)

```python
# src/models/gec_shared/shared_trainable_threshold.py
from .shared import GECSharedMLP

class GECSharedMLPTrainableThreshold(GECSharedMLP):
    """GEC_shared with trainable threshold routing."""

    def forward_threshold(self, x: Tensor, layer_idx: int = 0):
        # Similar dual-mode implementation
        # Use (G-1)/(G*E) formula for k calculation
        ...
```

#### 4. BaseGPT Updates (src/models/model_base.py)

```python
def _get_mlp_class(self) -> type:
    """Get MLP class, using trainable threshold variant if warmup enabled."""
    # Check training config for threshold warmup
    # Note: config passed during model creation must include training config
    use_trainable = getattr(self.config, 'threshold_warmup_steps', 0) > 0

    if self.config.model_type == "dense":
        return DenseMLP
    elif self.config.model_type == "gec":
        if use_trainable:
            from .gec import GECMLPTrainableThreshold
            return GECMLPTrainableThreshold
        from .gec import GECMLP
        return GECMLP
    elif self.config.model_type == "gec_shared":
        if use_trainable:
            from .gec_shared import GECSharedMLPTrainableThreshold
            return GECSharedMLPTrainableThreshold
        from .gec_shared import GECSharedMLP
        return GECSharedMLP
    # ... rest ...

def sync_cutoff_ema(self):
    """Sync cutoff EMA across GPUs (DDP only)."""
    import torch.distributed as dist
    if not dist.is_initialized():
        return

    for block in self.blocks:
        mlp = block.mlp
        if hasattr(mlp, 'cutoff_ema'):
            dist.all_reduce(mlp.cutoff_ema, op=dist.ReduceOp.AVG)
            if hasattr(mlp, 'cutoff_ema_count'):
                dist.all_reduce(mlp.cutoff_ema_count, op=dist.ReduceOp.AVG)

def set_routing_mode(self, mode: str):
    """Set routing mode for all MLP layers."""
    for block in self.blocks:
        if hasattr(block.mlp, 'routing_mode'):
            block.mlp.routing_mode = mode
```

**Problem**: ModelConfig doesn't have access to TrainingConfig!

**Solution**: Pass threshold_warmup_steps to ModelConfig during model creation

```python
# train.py
model_config = ModelConfig(**config.model)
model_config.threshold_warmup_steps = config.training.threshold_warmup_steps  # Pass through
```

Or cleaner: Add to ModelConfig as derived field:
```python
@dataclass
class ModelConfig:
    # ... existing ...
    threshold_warmup_steps: int = 0  # Passed from training config
```

#### 5. Training Loop (train.py)

```python
# Before loop (~line 180)
if config.training.threshold_warmup_steps > 0:
    orig_model.set_routing_mode('topk')
    print0(f"Starting with top-k, switching to threshold at step {config.training.threshold_warmup_steps}")

# Inside loop (~line 187)
for step in range(max_steps):
    t0 = time.time()

    # Mode switch
    if step == config.training.threshold_warmup_steps:
        orig_model.set_routing_mode('threshold')
        if ddp:
            orig_model.sync_cutoff_ema()
        print0(f"→ Switched to threshold routing")

    # ... training ...

    # After backward, before optimizer (~line 214)
    for micro_step in range(grad_accum_steps):
        # ... forward/backward ...
        loss.backward()
        x, y = next(data_loader)

    # Sync EMA if in threshold mode
    if ddp and step >= config.training.threshold_warmup_steps and \
       config.training.threshold_warmup_steps > 0:
        orig_model.sync_cutoff_ema()

    # Gradient clipping and optimizer step
    ...
```

---

## Testing Plan

### Test 1: Single GPU
```bash
CUDA_VISIBLE_DEVICES=0 python train.py \
  experiment=threshold_training \
  training.threshold_warmup_steps=10 \
  training.max_steps=50 \
  training.compile_model=false
```

**Verify**:
- Mode switches at step 10
- Loss continues to decrease
- No gradient errors

### Test 2: Multi-GPU EMA Sync
```bash
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 train.py \
  experiment=threshold_training \
  training.threshold_warmup_steps=10 \
  training.max_steps=50
```

**Verify**:
- Both GPUs have identical cutoff_ema after sync
- Training converges

### Test 3: Backward Compatibility
```bash
# Regular training (no threshold)
python train.py mlp=gec_shared training.threshold_warmup_steps=0
```

**Verify**:
- Uses original GECMLP class
- Works same as before

---

## Open Questions

1. **Config passing**: How to pass `threshold_warmup_steps` from TrainingConfig to ModelConfig?
   - Option A: Add as field to ModelConfig, populate in train.py
   - Option B: Check training config in `_get_mlp_class()` (need access to full Config)
   - **Decision**: Add to ModelConfig, populate from training config

2. **Benchmark updates**: Should we update threshold benchmarks to support training mode?
   - Not critical for this plan
   - Can be follow-up work

3. **torch.compile compatibility**: Will dual-mode work with compile?
   - Test without compile first
   - May need `dynamic=True` or disable compile for threshold training

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Training instability | High | Long warmup (10-20% of training), monitor loss |
| OOM from load imbalance | Medium | Using for-loop (sequential), no capacity needed |
| Distributed sync overhead | Low | Small tensors (<1ms), can measure |
| torch.compile incompatibility | Medium | Test without compile, use dynamic=True if needed |

---

## Success Criteria

- [ ] Threshold routing works in training mode (gradients flow)
- [ ] Cutoff EMA synchronized across GPUs
- [ ] Mode switching works correctly at warmup step
- [ ] Loss curves show convergence
- [ ] Backward compatible (threshold_warmup_steps=0 uses original)

---

## Next Steps

1. Implement Phase 1 (core classes)
2. Test single GPU training
3. Implement Phase 2 (training loop integration)
4. Test multi-GPU training
5. Create experiment config
6. Document design decisions
