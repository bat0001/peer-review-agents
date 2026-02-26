# W&B Hierarchical Logging Reorganization

**Status:** ✅ Completed (2025-10-04)

**Implementation:**
- Created `src/metrics_organizer.py` with hierarchical mapping
- Updated `src/logger.py` to use organizer for wandb (flat for console/JSON)
- All models use unified metric names (no prefixes)
- Representative layer metrics provide per-layer detail

**Archived design decisions:** See `memory/design/logging_architecture.md`

---

**Original plan follows below:**

---

## Problem

Current wandb logging has poor organization:
- **Flat structure**: All metrics at root level (loss, gec_expert_usage, grad_norm, throughput mixed together)
- **Limited hierarchy**: Only `eval/` prefix exists
- **Vector metrics lost**: Expert-level details (usage, cutoffs) are averaged across layers, losing per-layer information
- **Hard to navigate**: ~20-30 metrics in flat list, difficult to find related metrics in wandb UI

## Proposed Hierarchical Structure

```
train/
  loss                         # Training loss
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
    current/E{0-N}             # Current cutoff per expert (representative layer avg)
    ema/E{0-N}                 # EMA cutoff per expert (representative layer avg)
    temporal/                  # Phase 2: temporal metrics
      std                      # Std over last 100 steps
      delta                    # Step-to-step absolute change
      abs_deviation            # abs(current - ema).mean()

  expert_usage/E{0-N}          # Fraction of tokens per expert (representative layer avg)

  weights/                     # Phase 1: router activation stats
    mean                       # Average router confidence
    std                        # Router confidence variance
    max                        # Max confidence
    min                        # Min confidence

  logits/                      # Phase 3: pre-selection router logits
    mean                       # Average logit (can be negative)
    std                        # Logit variance

  layers/
    L{i}/                      # Representative layers only (i ∈ {0, n//4, n//2, 3n//4, n-1})
      E0_cutoff                # Expert 0 cutoff at this layer
      E0_cutoff_ema            # Expert 0 cutoff EMA at this layer
      E0_cutoff_temporal_std   # Phase 2: temporal std
      E0_cutoff_delta          # Phase 2: step-to-step change

system/
  throughput                   # Tokens/sec
  step_time                    # Time per step (seconds)
  gpu_util                     # GPU utilization %
  memory                       # GPU memory usage

chars/
  (keep existing character-level metrics)
```

## Implementation Plan

### Phase 1: Create Metrics Organizer

**File:** `src/metrics_organizer.py`

```python
class MetricsOrganizer:
    """Organize flat metrics into hierarchical wandb structure."""

    def __init__(self, model_type: str):
        self.model_type = model_type  # "gec", "ec", "gec_shared"
        self.prefix = self._get_prefix()

    def _get_prefix(self) -> str:
        """Get model-specific metric prefix."""
        if self.model_type == "gec_shared":
            return "gec_shared_"
        elif self.model_type == "ec":
            return "ec_"
        else:
            return "gec_"

    def organize(self, flat_metrics: Dict[str, float], step: int) -> Dict[str, float]:
        """Convert flat metrics to hierarchical structure."""
        hierarchical = {}

        for key, value in flat_metrics.items():
            # Route each metric to appropriate hierarchy
            organized_key = self._map_metric(key)
            if organized_key:
                hierarchical[organized_key] = value

        return hierarchical

    def _map_metric(self, key: str) -> Optional[str]:
        """Map flat metric key to hierarchical path."""

        # Training metrics
        if key == "loss":
            return "train/loss"
        if key == "learning_rate":
            return "train/lr"
        if key == "grad_norm":
            return "train/grad_norm"

        # System metrics
        if key in ["throughput", "step_time"]:
            return f"system/{key}"

        # Evaluation prefix
        eval_prefix = ""
        if key.startswith("eval/"):
            eval_prefix = "eval/"
            key = key[5:]  # Remove "eval/" prefix

        # Remove model-specific prefix
        if key.startswith(self.prefix):
            key = key[len(self.prefix):]

        # Coverage metrics
        if key == "avg_experts_per_token":
            return f"{eval_prefix}routing/coverage/avg_experts_per_token"
        if key == "max_experts_per_token":
            return f"{eval_prefix}routing/coverage/max_experts_per_token"
        if key == "tokens_with_no_expert":
            return f"{eval_prefix}routing/coverage/tokens_with_no_expert"
        if key.startswith("tokens_with_"):
            return f"{eval_prefix}routing/coverage/{key}"

        # Cutoffs (vector metrics - need expansion)
        if key == "cutoffs":
            # Will be expanded to per-expert metrics
            return None  # Handle separately in organize()
        if key == "cutoff_ema":
            return None  # Handle separately

        # Expert usage (vector metric)
        if key == "expert_usage":
            return None  # Handle separately

        # Representative layer metrics
        if key.startswith("repr_L"):
            # e.g., "ec_repr_L0_E0_cutoff" -> "routing/layers/L0/E0_cutoff"
            parts = key.split("_", 2)  # ["repr", "L0", "E0_cutoff"]
            layer = parts[1]
            metric = parts[2]
            return f"{eval_prefix}routing/layers/{layer}/{metric}"

        # Temporal metrics (Phase 2)
        if "temporal" in key or "delta" in key or "abs_deviation" in key:
            return f"{eval_prefix}routing/cutoffs/temporal/{key}"

        # Activation weights (Phase 1)
        if "activation_weight" in key:
            stat = key.split("_")[-1]  # mean, std, max, min
            return f"{eval_prefix}routing/weights/{stat}"

        # Router logits (Phase 3)
        if "router_logit" in key:
            stat = key.split("_")[-1]  # mean, std
            return f"{eval_prefix}routing/logits/{stat}"

        # Model-specific metrics
        if key == "n_chunks":
            return f"{eval_prefix}routing/n_chunks"
        if key.startswith("avg_routed_"):
            return f"{eval_prefix}routing/coverage/{key}"

        # Fallback: keep at root
        return key
```

### Phase 2: Update Logger

**File:** `src/logger.py` (modifications)

```python
class Logger:
    def __init__(self, config: Any, output_dir: Path, rank: int = 0, model_type: str = "gec"):
        # ... existing code ...

        # Initialize metrics organizer
        from .metrics_organizer import MetricsOrganizer
        self.metrics_organizer = MetricsOrganizer(model_type)

    def log_metrics(
        self,
        step: int,
        metrics: Dict[str, float],
        prefix: str = ""
    ) -> None:
        """Log metrics."""
        if not self.should_log:
            return

        # Format metrics for console/file (keep flat)
        flat_metrics = {}
        for key, value in metrics.items():
            formatted_key = f"{prefix}{key}"
            flat_metrics[formatted_key] = value

        # Console log (flat)
        metrics_str = ", ".join(f"{k}: {v:.4f}" for k, v in flat_metrics.items())
        self.log(f"Step {step}: {metrics_str}")

        # Wandb log (hierarchical)
        if self.use_wandb:
            hierarchical_metrics = self.metrics_organizer.organize(flat_metrics, step)
            wandb.log(hierarchical_metrics, step=step)

        # JSON log (flat for backward compatibility)
        json_log = {
            'step': step,
            'metrics': flat_metrics,
            'timestamp': datetime.now().isoformat()
        }

        json_file = self.output_dir / "metrics.jsonl"
        with open(json_file, 'a') as f:
            f.write(json.dumps(json_log) + '\n')
```

### Phase 3: Update Trainer to Pass Model Type

**File:** `src/trainer.py` (modifications)

```python
def _setup_logging(self) -> None:
    """Initialize logging."""
    self.logger = Logger(
        config=self.config.logging,
        output_dir=self.output_dir,
        rank=self.rank,
        model_type=self.config.model.model_type  # Pass model type
    )
```

### Phase 4: Expand Vector Metrics (Optional Enhancement)

For per-expert metrics (cutoffs, expert_usage), expand vectors to individual wandb entries:

```python
def _expand_vector_metrics(self, metrics: Dict[str, Any]) -> Dict[str, float]:
    """Expand vector metrics to per-expert entries."""
    expanded = {}

    for key, value in metrics.items():
        if isinstance(value, torch.Tensor) and value.ndim == 1:
            # Vector metric - expand to per-expert
            if "cutoffs" in key:
                for i, v in enumerate(value):
                    expanded[f"routing/cutoffs/current/E{i}"] = v.item()
            elif "cutoff_ema" in key:
                for i, v in enumerate(value):
                    expanded[f"routing/cutoffs/ema/E{i}"] = v.item()
            elif "expert_usage" in key:
                for i, v in enumerate(value):
                    expanded[f"routing/expert_usage/E{i}"] = v.item()
        else:
            # Scalar metric - pass through
            expanded[key] = value

    return expanded
```

## Benefits

1. **Better navigation**: Related metrics grouped in wandb UI
2. **Scalability**: Easy to add temporal/spatial metrics without clutter
3. **Expert-level detail**: Track per-expert cutoffs/usage at representative layers
4. **Consistency**: Unified structure across GEC/EC/GEC_shared models
5. **No breaking changes**: Console/file logs remain flat for backward compatibility

## Rollout

1. ✅ Create `src/metrics_organizer.py` with basic mapping
2. ✅ Update `src/logger.py` to use organizer for wandb logging only
3. ✅ Update `src/trainer.py` to pass model_type to Logger
4. ✅ Test with small training run, verify wandb UI shows hierarchy
5. 🔲 Add Phase 1 metrics (tokens_with_1_expert, activation_weight_mean/std, cutoff_abs_deviation)
6. 🔲 Expand vector metrics to per-expert entries (optional)
7. 🔲 Add Phase 2 temporal metrics (cutoff_temporal_std, cutoff_delta)

## Testing

```bash
# Run small training with hierarchical logging
python train.py --config configs/gec.yaml --max-steps 100

# Check wandb UI:
# - train/ should have loss, lr, grad_norm
# - routing/coverage/ should have avg_experts_per_token, etc.
# - routing/layers/L{i}/ should have per-layer metrics
# - system/ should have throughput, step_time
```

## Notes

- Console and JSON logs remain **flat** for backward compatibility
- Only wandb logging uses hierarchical structure
- Vector metrics (expert_usage, cutoffs) currently averaged across layers
  - Can expand to per-expert metrics in Phase 4 if needed
- Representative layer metrics already track per-layer detail
