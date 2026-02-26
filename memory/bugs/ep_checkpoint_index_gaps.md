# EP Checkpoint Expert Index Gaps

**Status:** Resolved (2026-01-27)

## Summary
Expert-parallel (EP) checkpoints saved by `train.py` could contain *gapped* expert indices
per layer (e.g., `0,1,22,23,44,45,...`) instead of contiguous `0..n_routed_experts-1`.
This breaks strict `load_state_dict` in non-EP analysis/eval scripts.

## Symptoms
- `RuntimeError: Missing key(s) ... expert_weight1.2 ... Unexpected key(s) ... expert_weight1.22 ...`
- Only affects EP runs (typically run directory suffix `_ep` or `_ep8`).

## Root Cause
`train.py:save_checkpoint` computed `local_experts` by **counting all expert_weight keys**
on a rank, which includes *all layers*, not just a single layer. With `first_layer_dense=true`,
this inflated `local_experts` by the number of expert layers, causing global indices like
`r * 22 + local_idx` instead of `r * 2 + local_idx`.

## Fix
- **Code fix (prevention):** `train.py` now derives `local_experts` from config
  (`n_routed_experts // world_size`), not by counting keys.
- **Mitigation (existing checkpoints):** `script/archived/fix_ep_checkpoint_indices.py` rewrites
  per-layer `expert_weight{1,2}` indices to be contiguous and saves `*_fixed.pt`.

## Verification
- Load `_fixed` checkpoints with `strict=True`.
- Spot-check any layer to ensure indices are `0..n_routed_experts-1` with no gaps.

## Practical Note (2026-02-11)

During 2-GPU CORE eval validation of batched prefill/model-side shape alignment, EP checkpoint
index repair was required before loading with strict state dict checks:

- Input:
  - `.../checkpoint_step_100.pt`
- Repaired:
  - `.../checkpoint_step_100_fixed.pt`

Repair command used:

```bash
/data2/hanchi/miniconda3/envs/nanochat/bin/python - <<'PY'
from pathlib import Path
from script.archived.fix_ep_checkpoint_indices import fix_checkpoint
fix_checkpoint(Path("outputs/gec_shared_d8_G2E8_0.01B_ep8/gec_shared_d8_G2E8_0.01B_ep8/checkpoints/checkpoint_step_100.pt"))
PY
```

## Affected Runs
EP runs with suffix `_ep` / `_ep8` (e.g., d12/d20 GEC/GEC_shared EP).
