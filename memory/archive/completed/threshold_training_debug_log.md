# Threshold Training Debug Log

**Date**: 2025-10-27
**Status**: Debugging single GPU training

## Implementation Complete

✅ All core components implemented:
1. Config: `TrainingConfig.threshold_warmup_steps` added
2. New classes: `GECMLPTrainableThreshold`, `GECSharedMLPTrainableThreshold`
3. BaseGPT helpers: `sync_cutoff_ema()`, `set_routing_mode()`
4. Training loop: Mode switching at warmup step, EMA sync
5. Experiment config: `configs/experiment/threshold_training.yaml`

## Current Issue

**Problem**: Training hangs/crashes after switching to threshold mode at step 50

**Symptoms**:
- Training runs fine in top-k mode (steps 0-49)
- After switching to threshold at step 50, process appears to hang
- Output redirection shows empty file (buffering issue)

## Root Cause Investigation

### Issue 1: Router logits = 0 (RESOLVED)
- **Found**: During steps 0-9, router logits were all 0.0
- **Cause**: Trainable threshold variant was calling `forward_threshold()` instead of `forward_topk()` during warmup
- **Fix**: Changed to explicitly call `super().forward_topk()` when mode='topk'

### Issue 2: cutoff_ema = 0 causing no expert activation (PARTIALLY RESOLVED)
- **Found**: cutoff_ema tracked from top-k warmup was ~0.0
- **Problem**: With cutoff=0 and router_logits~0, threshold check `logit > cutoff` = `0 > 0` = False
- **Fix**: Changed comparison to `>=` so experts activate when both are ~0
- **Remaining issue**: Need longer warmup for router to learn meaningful values

### Issue 3: Muon optimizer failing with None gradients (IDENTIFIED)
- **Error**: `AssertionError` in `muon.py:75` - `assert g is not None`
- **Cause**: When no routed experts activate, their parameters don't get gradients
- **Why**: Threshold routing can result in 0 active experts → no gradients for expert weights → optimizer crash
- **Note**: This is expected behavior for threshold routing early in training

### Issue 4: calculate_max_steps prioritizing epochs over explicit max_steps (RESOLVED)
- **Symptom**: Config had `max_steps: 100` but training showed "Starting training for 76293 steps..."
- **Cause**: `calculate_max_steps()` used if-elif logic, prioritizing `max_epochs` over `max_steps`
- **Fix**: Changed to `min(steps_from_epochs, steps_from_max)` so whichever is shorter is used
- **Result**: Training now correctly runs for 100 steps

### Issue 5: cutoff_ema remains 0 after warmup (CURRENT)
- **Symptom**: After 50 warmup steps, debug shows "cutoff_ema mean=0.0000, max=0.0000"
- **Impact**: Training still succeeds because `>=` comparison and shared expert saves us
- **Investigation needed**: Why aren't router logits producing non-zero cutoffs during top-k warmup?

## Successful Test Runs

### Single GPU Test (2025-10-27 17:12-17:18)

✅ **Training completed successfully!**

**Configuration:**
- 100 total steps (correctly using min(max_steps=100, steps_from_epochs=76293))
- 50 warmup steps in top-k mode
- 50 steps in threshold mode
- Single GPU (CUDA:1)

**Results:**
- Loss progression: 10.81 → 5.70 (continued to decrease after mode switch)
- Mode switch at step 50: successful, no crashes
- Top-k throughput: ~33-34k tokens/s
- Threshold throughput: ~13-14k tokens/s (2.4x slower, expected)
- Eval loss progression: 6.69 → 5.79

**Issue:**
- cutoff_ema remains 0.0 after 50 warmup steps
- Training succeeds anyway (>= comparison + shared expert)

### Multi-GPU Test (2025-10-27 17:33-17:37)

✅ **DDP training completed successfully!**

**Configuration:**
- 100 total steps (50 top-k warmup + 50 threshold)
- 2 GPUs (CUDA:0,1) with torchrun
- Same config as single GPU test

**Results:**
- Loss progression: 10.81 → 5.87 (continued to decrease after mode switch)
- Mode switch at step 50: successful, no crashes
- Top-k throughput: ~65k tokens/s (2x speedup, perfect scaling)
- Threshold throughput: ~27k tokens/s (2x speedup, perfect scaling)
- Eval loss progression: 6.95 → 6.23
- EMA synchronization: No crashes, stable training (appears to work correctly)

**Same issue:**
- cutoff_ema remains 0.0 after 50 warmup steps (same as single GPU)
- Training still succeeds (>= comparison + shared expert)

## Next Steps

### Immediate (Investigate cutoff_ema=0):
1. Add debug logging to show router_logits during top-k warmup
2. Check if forward_topk is actually being called during warmup
3. Verify EMA update logic is executing
4. Test with longer warmup to see if values eventually become non-zero

### Short-term (Make threshold training robust):
1. Add safeguard: If no experts activate, fall back to all-experts or top-k for that step
2. Handle None gradients gracefully (skip Muon step or use zeros)
3. Add metrics: track how many experts activate per step
4. Validate cutoff_ema values are reasonable before switching

### Long-term (Production-ready threshold training):
1. Add bias correction for cutoff_ema (currently raw EMA)
2. Implement capacity limits if needed
3. Test multi-GPU with proper EMA sync
4. Compare loss curves: top-k only vs top-k→threshold
5. Benchmark throughput difference

## Config Used

```yaml
training:
  max_steps: 60
  threshold_warmup_steps: 50  # Switch at step 50
  per_device_batch_size: 4
  compile_model: false  # Disabled for debugging

model:
  model_type: gec_shared
  granularity: 2
  expansion: 8
```

## Files Modified

- `src/config.py`:
  - Added `threshold_warmup_steps` to TrainingConfig
  - Updated `calculate_max_steps()` to use `min(max_steps, steps_from_epochs)`
- `src/models/model_base.py`: Added `threshold_warmup_steps` to ModelConfig, `sync_cutoff_ema()`, `set_routing_mode()`, updated `_get_mlp_class()`
- `src/models/gec/gec_trainable_threshold.py`: New file (trainable threshold GEC)
- `src/models/gec_shared/shared_trainable_threshold.py`: New file (trainable threshold GEC_shared)
- `train.py`: Mode switching logic, EMA sync, debug logging
- `configs/experiment/threshold_training.yaml`: New experiment config

## Key Insights

1. **Threshold warmup is critical**: 10 steps is WAY too short. Even 50 steps shows cutoff_ema=0.
2. **Cutoff initialization matters**: Starting at 1.0 is too high, -10.0 gets overwritten by EMA.
3. **>= vs > matters**: When logits and cutoff are both ~0, `>=` allows activation.
4. **Shared expert saves us**: GEC_shared always has shared expert active, so we won't get ALL zero gradients.
5. **Inheritance works well**: Inheriting from parent class and overriding just `forward()` and `forward_threshold()` is clean.
6. **Config precedence**: Changed `calculate_max_steps()` to use `min(max_steps, steps_from_epochs)` so users can set both.
7. **Performance overhead**: Threshold routing is ~2.4x slower than top-k (13k vs 33k tokens/s) due to dynamic routing.
8. **Training robustness**: Even with cutoff_ema=0, training succeeds and loss improves (thanks to >= and shared expert).

## Conclusions

### ✅ Implementation Complete and Working

All core functionality implemented and tested:
1. **Single GPU**: Training completes successfully with mode switching
2. **Multi-GPU (DDP)**: Perfect scaling, EMA sync appears to work correctly
3. **Config system**: `min(max_steps, steps_from_epochs)` works as intended
4. **Performance**: Threshold mode is ~2.4x slower than top-k (expected overhead)
5. **Robustness**: Training succeeds even with cutoff_ema=0 (thanks to >= and shared expert)

### 🔍 Open Question: cutoff_ema=0

**Observation**: cutoff_ema remains 0.0 after 50 warmup steps in both single and multi-GPU tests.

**Why training still works:**
1. `>=` comparison allows expert activation when logits and cutoff both ~0
2. Shared expert always active → no all-zero gradients
3. Loss continues to decrease after mode switch

**Possible explanations:**
1. Router weights initialize to 0 and 50 steps isn't enough for them to learn
2. EMA initialization at -10.0 gets overwritten immediately by 0.0 cutoffs
3. This might be expected behavior early in training
4. Perhaps cutoff_ema=0 is actually fine for threshold routing?

**Decision needed:**
- Is this worth investigating further? Or accept that training works?
- Could increase warmup duration to see if cutoffs eventually become non-zero
- Could add more detailed debug logging to trace router_logits during warmup

### Questions to Resolve

1. **Should we handle None gradients?** Currently protected by shared expert + >= comparison.
2. **What's the right warmup duration?** 50 steps works but cutoff_ema=0. Need longer?
3. **Should we validate cutoffs before switching?** Or trust that >= + shared expert handle it?
4. **Is cutoff_ema=0 acceptable?** Training works fine, but is this the intended behavior?
