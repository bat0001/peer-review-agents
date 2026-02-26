# Zero-Init Expert Down Projections

**Date:** 2025-12-09 → **Completed:** 2025-12-13
**Status:** ✅ Completed (implemented as default, no config option)

## Summary

Expert down projections (`expert_weight2`, `shared_weight2`) are now zero-initialized by default, matching nanochat's pattern for all output projections.

## Implementation

**Decision:** Instead of adding a config option, we made zero-init the default behavior. This matches nanochat exactly and simplifies the codebase.

**Change made in `src/models/model_base.py:460-464`:**
```python
# 2. Output projections (zero init, critical for Muon)
# Includes: lm_head, c_proj, expert_weight2, shared_weight2
elif 'lm_head.weight' in name or 'c_proj.weight' in name or 'weight2' in name:
    torch.nn.init.zeros_(param)
    initialized.add(id(param))
```

## Test updated

`test/test_weight_init.py` now expects zero for `weight2` parameters.

## Experiment

**Experiment 4** (`script/run_gec_shared_ep.sh` with `gec_shared_epx8_zeroinit`) tests this hypothesis:
- Expected: Smaller initial grad norm, potentially better loss curves, may resolve L0 oscillations
