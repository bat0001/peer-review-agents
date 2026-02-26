# Plan: Absorb Hardcoded Values into Config

> **DEPRECATED** (2025-12): Deprioritized in favor of EP work. Low priority cleanup task.

## Summary

Move hardcoded values from `train.py` into the config system for better experiment control.

## Issues to Fix

### 1. **Muon Momentum Schedule Not Using Config** (Critical)
`train.py:166-169` hardcodes values that already exist in config:
```python
def get_muon_momentum(it):
    frac = min(it / 300, 1)  # Hardcoded! Config has muon_momentum_warmup_steps
    return (1 - frac) * 0.85 + frac * 0.95  # Hardcoded! Config has start/end
```

### 2. **Evaluation Batch Count Hardcoded**
`train.py:352`: `num_batches = 10` - should be configurable.

---

## Changes

### File: `src/config.py`

Add to `TrainingConfig`:
```python
eval_batches: int = 10  # Number of batches for evaluation
```

### File: `train.py`

1. **Lines 166-169**: Use config for Muon momentum schedule:
   ```python
   def get_muon_momentum(it):
       warmup_steps = opt_config.get('muon_momentum_warmup_steps', 300)
       start = opt_config.get('muon_momentum_start', 0.85)
       end = opt_config.get('muon_momentum_end', 0.95)
       frac = min(it / warmup_steps, 1) if warmup_steps > 0 else 1.0
       return (1 - frac) * start + frac * end
   ```

2. **Line 352**: Use config eval_batches:
   ```python
   num_batches = config.training.eval_batches
   ```

### File: `configs/training/*.yaml`

Add default to each training config:
```yaml
eval_batches: 10
```

---

## Files to Modify

1. `src/config.py` - Add `eval_batches` field
2. `train.py` - Use config values for Muon momentum and eval_batches
3. `configs/training/quick.yaml`
4. `configs/training/standard.yaml`
5. `configs/training/long.yaml`
