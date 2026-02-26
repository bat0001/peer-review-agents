# Utils Module

Metrics, logging, and evaluation utilities for GEC training.

## Overview

This module contains all metrics tracking, logging, and evaluation infrastructure. These components are separated from core model/training code to keep the runtime implementation clean and focused.

## Module Contents

### `metrics.py` - MetricsTracker
Tracks and aggregates training metrics across steps.

**Key features:**
- Per-step metric updates
- Rolling averages over last N steps
- Summary statistics (mean, std, min, max)
- State save/load for checkpoints

**Usage:**
```python
from src.utils import MetricsTracker

tracker = MetricsTracker()
tracker.update({'loss': 2.5, 'grad_norm': 1.2})
avg_loss = tracker.get_average('loss', last_n=100)
```

### `logger.py` - Logger
Handles console, file, and wandb logging.

**Key features:**
- Rank-aware logging (only rank 0 logs)
- Console + file output
- Optional wandb integration
- Hierarchical metric organization via MetricsOrganizer

**Usage:**
```python
from src.utils import Logger

logger = Logger(config.logging, output_dir, rank=0)
logger.log_metrics(step=100, metrics={'loss': 2.5})
logger.finish()
```

### `metrics_organizer.py` - MetricsOrganizer
Converts flat metric dictionaries to hierarchical wandb paths.

**Hierarchy:**
- `train/loss`, `train/lr`, `train/grad_norm`
- `eval/loss`
- `routing/coverage/`, `routing/cutoffs/`, `routing/weights/`
- `routing/layers/L{i}/`
- `system/throughput`, `system/step_time`

**Usage:**
```python
from src.utils import MetricsOrganizer

organizer = MetricsOrganizer()
flat = {'loss': 2.5, 'avg_experts_per_token': 3.2}
hierarchical = organizer.organize(flat)  # {'train/loss': 2.5, 'routing/coverage/avg_experts_per_token': 3.2}
```

### `routing_metrics.py` - compute_routing_metrics()
Computes comprehensive routing statistics for GEC/EC models.

**Extracted from:** RouterMixin (was a method, now standalone function)

**Metrics computed:**
- Expert usage distribution
- Token fanout statistics (0, 1, 2+ experts per token)
- Routing cutoffs and EMA tracking
- Activation weight statistics
- Router logit statistics
- Representative layer metrics with temporal tracking

**Usage:**
```python
from src.utils import compute_routing_metrics

metrics = compute_routing_metrics(
    cutoffs=cutoffs,
    cutoff_ema=cutoff_ema,
    weights=weights,
    router_logits_flat=router_logits_flat,
    token_fanout=token_fanout,
    expert_usage=expert_usage,
    layer_idx=0,
    n_layer=12,
    model_instance=self,  # For temporal tracking buffers
    router_activation='sigmoid',
)
```

### `visualizer.py` - EvalVisualizer
Generates routing behavior visualizations during evaluation.

**Key features:**
- Self-contained data extraction from model outputs
- Two-level output: JSON logs (every eval_interval) and plots (every plot_interval)
- Processes representative layers only (first, middle, last)
- Minimal overhead during training

**Visualizations generated:**
1. **JSON logs** (every eval_interval):
   - Expert activation histogram
   - Router weight percentiles

2. **Plots** (every plot_interval):
   - Router weight CDF
   - Loss distribution by expert count (violin plot)
   - Expert cutoff distribution
   - Token entropy vs expert count (violin plot)

**Usage:**
```python
from src.utils import EvalVisualizer

# Initialize in trainer
visualizer = EvalVisualizer(config, output_dir, num_layers)

# During evaluation
visualizer.clear_accumulated_data()
for batch in eval_batches:
    output = model(input_ids, labels)
    visualizer.accumulate_batch(output, labels, output.layer_data)

# After evaluation
visualizer.log_eval_stats(step)
if step % plot_interval == 0:
    visualizer.create_plots(step)
```

**Configuration:**
```yaml
training:
  enable_visualizations: true  # Enable visualization
  plot_interval: 5000  # Generate plots every N steps (defaults to save_interval)
```

**Output structure:**
```
{output_dir}/
├── eval_logs/
│   ├── expert_counts.json
│   └── weight_percentiles.json
└── visualizations/
    ├── step_5000/
    │   ├── weight_cdf/
    │   ├── loss_by_experts/
    │   ├── cutoff_vs_loss/
    │   └── entropy_vs_experts/
    └── step_10000/
        └── ...
```

## Design Rationale

**Why separate from core?**

1. **Core code focus**: Model implementations (`src/models/`) focus on forward/backward passes
2. **Training code focus**: Trainer (`src/trainer.py`) focuses on optimization loop
3. **Clean separation**: Metrics/eval code is infrastructure, not runtime logic
4. **Easy to extend**: Add new metrics/visualizations without touching core

**What stays in core:**
- `RouterMixin.apply_router_activation()` - Used in forward pass
- `RouterMixin.compute_normalizer()` - Used in forward pass

**What moved to utils:**
- All metrics tracking and aggregation
- All logging (console, file, wandb)
- Routing metrics computation (extracted from RouterMixin)
- Evaluation visualizations (routing behavior analysis)

## Refactoring History

**Oct 2025**: Moved metrics/eval infrastructure from `src/` to `src/utils/`
- `src/metrics.py` → `src/utils/metrics.py`
- `src/logger.py` → `src/utils/logger.py`
- `src/metrics_organizer.py` → `src/utils/metrics_organizer.py`
- `RouterMixin.compute_routing_metrics()` → `src/utils/routing_metrics.py` (standalone function)

**Oct 2025**: Added evaluation visualizations
- New module: `src/utils/visualizer.py` (EvalVisualizer)
- Added `layer_data` field to ModelOutput for per-layer routing data
- GEC/EC models now include raw routing data in metrics during eval

**Imports updated:**
- `src/trainer.py`: `from .utils import MetricsTracker, Logger, EvalVisualizer`
- `src/models/gec/*.py`, `src/models/ec.py`: `from ...utils import compute_routing_metrics`
