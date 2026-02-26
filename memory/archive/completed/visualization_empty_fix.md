# Debugging: Empty Visualization Directory

**Date**: 2025-10-07
**Issue**: `outputs/debug-viz/visualizations/` remains empty despite `enable_visualizations: true`

## Root Cause

**Actual root cause**: The MLP has TWO forward paths - `forward_topk()` for training and `forward_threshold()` for evaluation. The dispatcher at `forward()` uses `self.training` to route between them:

```python
# src/models/gec_shared/shared.py:101-106
def forward(self, x, layer_idx=0):
    if self.training:
        return self.forward_topk(x, layer_idx)   # Training path
    else:
        return self.forward_threshold(x, layer_idx)  # Eval path
```

**Problem**: `layer_data` collection was only implemented in `forward_topk()` (lines 235-242), but NOT in `forward_threshold()`. During eval, `forward_threshold()` was being called, which returns metrics WITHOUT `layer_data`.

**Initial misdiagnosis**: Debug investigation initially focused on `self.training` not being False during eval, but actually the dispatcher was working correctly - it was routing to `forward_threshold()`, which simply didn't have the visualization code.

## Solution

Added `layer_data` collection to `forward_threshold()` (eval path):

```python
# src/models/gec_shared/shared.py:325-335 (added after computing metrics)
# Add raw layer data for visualization (during eval only)
# Threshold routing is eval-only, so always collect layer_data
if not torch.is_grad_enabled():
    # Compute weights for visualization (same as in topk - sigmoid of router logits)
    weights = torch.sigmoid(router_logits_flat)
    metrics['layer_data'] = {
        'weights': weights.view(-1).detach(),
        'fanout': token_fanout_with_shared.detach(),
        'cutoffs': self.cutoff_ema.clone().detach(),
        'router_logits': router_logits_flat.detach(),
    }
```

**Note**: Also used `torch.is_grad_enabled()` check instead of assuming eval mode, for consistency with the topk path and safety against future code changes.

## Visualization Pipeline Flow

1. **Model forward** (eval mode, `torch.no_grad()`):
   - MLP checks `torch.is_grad_enabled()` → False during eval
   - Adds `layer_data` to metrics dict
   - Block passes metrics up unchanged
   - Model collects `layer_data` from representative layers (0, n_layer//2, n_layer-1)
   - Returns `ModelOutput(logits, loss, metrics, layer_data)`

2. **Trainer evaluation** (src/trainer.py:238-272):
   - Calls `model.eval()` and enters `torch.no_grad()`
   - Clears visualizer accumulated data
   - For each eval batch:
     - Gets model output
     - Passes `output.layer_data` to `visualizer.accumulate_batch()`
   - After all batches:
     - Calls `visualizer.log_eval_stats(step)` → Writes JSON logs
     - If `step % plot_interval == 0`: calls `visualizer.create_plots(step)` → Generates PNG plots

3. **Output structure**:
   ```
   outputs/debug-viz/
   ├── eval_logs/
   │   ├── expert_counts.json       # Lightweight stats per eval
   │   └── weight_percentiles.json
   └── visualizations/
       └── step_{N}/                # Generated at plot_interval
           ├── weight_cdf/
           ├── loss_by_experts/
           ├── cutoff_vs_loss/
           └── entropy_violin/
   ```

## Related Code Locations

- **MLP forward dispatcher**: `src/models/gec_shared/shared.py:101-106`
- **MLP layer_data (topk path)**: `src/models/gec_shared/shared.py:236-242`
- **MLP layer_data (threshold path)**: `src/models/gec_shared/shared.py:325-335` (ADDED)
- **Model layer_data aggregation**: `src/models/model_base.py:465-476`
- **Trainer eval + visualization**: `src/trainer.py:238-272`
- **Visualizer implementation**: `src/utils/visualizer.py`
- **Config flags**: `training.enable_visualizations`, `training.plot_interval` in YAML configs

## Testing Status

- ✅ Identified root cause: `forward_threshold()` missing layer_data collection
- ✅ Applied fix: added layer_data to `forward_threshold()`
- ✅ Verified visualizations are generated (step_50 plots created)
- ✅ Cleaned up all debug prints

## Next Steps

1. Apply same fix to other MLP variants (GEC, EC) that have dual forward paths
