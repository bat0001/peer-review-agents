# Logging Architecture

## Design Principles

1. **Dual structure**: Flat for console/JSON (backward compatible), hierarchical for wandb (easy navigation)
2. **No model prefixes**: All models (GEC, EC, GEC_shared) use identical metric names
3. **Model identification**: Via wandb run config/name, not metric prefixes
4. **Single organizer**: One `MetricsOrganizer` class handles all hierarchical mapping

## Hierarchical Structure (Wandb)

```
train/
  loss                         # Training loss
  loss_ema                     # Unbiased EMA of training loss (decay=0.999)
  lr                           # Learning rate
  grad_norm                    # Gradient norm

eval/
  loss                         # Eval loss
  routing/                     # Eval routing metrics (same structure as train/routing)
    ...

routing/
  coverage/
    avg_experts_per_token      # Average fanout
    max_experts_per_token      # Max fanout
    tokens_with_no_expert      # Fraction unprocessed
    tokens_with_1_expert       # Exactly 1 expert (no overlap)
    tokens_with_2+_experts     # Multiple experts (has overlap)

  cutoffs/
    current                    # Current cutoff (vector logged as array)
    ema                        # EMA cutoff (vector logged as array)
    temporal/
      abs_deviation            # abs(current - ema).mean()

  expert_usage                 # Usage per expert (vector logged as array)

  weights/                     # Router activation stats
    mean                       # Average router confidence
    std                        # Router confidence variance
    max                        # Max confidence
    min                        # Min confidence

  logits/                      # Pre-selection router logits
    mean                       # Average logit (can be negative)
    std                        # Logit variance

  layers/
    L{i}/                      # Representative layers only (i ∈ {0, n//4, n//2, 3n//4, n-1})
      E0_cutoff                # Expert 0 cutoff at this layer
      E0_cutoff_ema            # Expert 0 cutoff EMA at this layer
      E0_cutoff_temporal_std   # Temporal std over last 100 steps
      E0_cutoff_delta          # Step-to-step change

system/
  throughput                   # Tokens/sec
  step_time                    # Time per step (seconds)
  gpu_util                     # GPU utilization % (if tracked)
  memory                       # GPU memory usage (if tracked)

chars/
  (keep existing character-level metrics)
```

## Implementation: MetricsOrganizer

**File**: `src/metrics_organizer.py`

Single class that maps flat metric keys to hierarchical paths:

```python
class MetricsOrganizer:
    """Convert flat model metrics to hierarchical wandb paths."""

    def organize(self, flat_metrics: Dict[str, float]) -> Dict[str, float]:
        """Convert flat metrics to hierarchical structure."""
        hierarchical = {}
        for key, value in flat_metrics.items():
            new_key = self._map_metric(key)
            hierarchical[new_key] = value
        return hierarchical

    def _map_metric(self, key: str) -> str:
        """Map flat metric key to hierarchical path."""
        # Handle eval prefix
        # Route to train/, routing/, system/, etc.
```

**Key features:**
- No `model_type` parameter needed (all models use same names)
- Handles `eval/` prefix by prepending to hierarchical path
- Vector metrics logged as arrays (not expanded to per-expert entries)

## Implementation: Logger

**File**: `src/logger.py`

```python
class Logger:
    def __init__(self, config: Any, output_dir: Path, rank: int = 0):
        # No model_type parameter
        self.metrics_organizer = MetricsOrganizer()

    def log_metrics(self, step: int, metrics: Dict[str, float], prefix: str = ""):
        # Console/JSON: flat
        flat_metrics = {f"{prefix}{k}": v for k, v in metrics.items()}

        # Wandb: hierarchical
        if self.use_wandb:
            hierarchical = self.metrics_organizer.organize(flat_metrics)
            wandb.log(hierarchical, step=step)

        # JSON: flat (backward compatible)
        json_log = {'step': step, 'metrics': flat_metrics, ...}
```

## Benefits

1. **Better navigation**: Related metrics grouped in wandb UI folders
2. **Direct comparison**: Overlay GEC/EC/GEC_shared runs (same metric names)
3. **Backward compatible**: Console/JSON logs unchanged
4. **Scalability**: Easy to add new metric categories without clutter
5. **Simplicity**: Single organizer class, no model-specific logic

## Design Decisions

### Why no model prefixes?

**Old approach:**
```
gec_expert_usage
ec_expert_usage
gec_shared_expert_usage
```

**New approach:**
```
expert_usage  (all models)
```

**Rationale:**
- All models track the same concepts (fanout, cutoffs, weights)
- Model type identified by wandb run name/config (e.g., "gpt2-gec-16a2" vs "gpt2-ec-16a2")
- Enables direct comparison in wandb (overlay multiple runs)
- Cleaner hierarchy: `routing/coverage/avg_experts_per_token` vs `routing/coverage/gec_avg_experts_per_token`

### Why not expand vector metrics to per-expert entries?

**Alternative approach:**
```
routing/cutoffs/current/E0
routing/cutoffs/current/E1
...
routing/cutoffs/current/E7
```

**Current approach:**
```
routing/cutoffs/current  (logged as array)
```

**Rationale:**
- Avoids metric explosion (8 experts × 2 metrics × 2 modes = 32 extra wandb series)
- Wandb handles arrays well (can plot, compare)
- Can add per-expert expansion later if needed
- Representative layer metrics already provide per-layer detail

### Why separate organizer class?

**Alternative:** Put mapping logic in Logger

**Current:** Separate `MetricsOrganizer` class

**Rationale:**
- Single responsibility: Logger handles logging, Organizer handles mapping
- Easier to test mapping logic in isolation
- Can reuse organizer for other purposes (e.g., custom metric exporters)
- Cleaner code: Logger doesn't need to know hierarchical structure details

### Why flat console/JSON logs?

**Rationale:**
- Backward compatibility with existing scripts/analysis tools
- Easier to grep/parse flat structure
- Console output more readable with short keys
- JSON logs used for quick inspection, not deep analysis

## Migration Notes

**From old flat structure:**
- Old: All metrics at root level
- New: Wandb hierarchical, console/JSON flat
- No breaking changes to existing code

**Removed during implementation:**
- Model prefixes (`gec_`, `ec_`, `gec_shared_`)
- `model_type` parameter in Logger
- Per-expert metric expansion (deferred as optional enhancement)
