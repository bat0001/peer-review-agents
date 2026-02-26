# Eval Visualization Plan (Condensed)

## Overview

Static behavior visualizations to understand expert routing patterns during evaluation.

**Key Design Choices**:
- **Single configuration flag**: `enable_visualizations: bool = True` (default on, minimal overhead)
- **Two levels of output**: Lightweight JSON logging (every eval_interval) and full plots (every plot_interval)
- **Hook into evaluate()**: Reuse existing validation iteration, no redundant passes
- **Exact statistics**: Collect full data for 3 representative layers (~2GB memory is acceptable)
- **plot_interval**: Controls plot generation frequency (defaults to save_interval, but has nothing to do with checkpoint saving)

---

## Data Collection Timing

### During Training (every step)
- **Nothing** - Keep training loop fast

### During Eval (eval_interval, ~500 steps)
- **Hook**: Called within `Trainer.evaluate()` during existing validation pass
- **Data collection**: Accumulate exact statistics for 3 representative layers as we iterate validation set
- **JSON logging**: Compute and append lightweight statistics to time-series files
- **Dataset**: Full validation set (~100M tokens)
- **Memory**: ~2GB to accumulate data for representative layers
- **No extra passes**: Piggyback on existing validation iteration

### When step % plot_interval == 0 (typically ~5000 steps)
- **During the same eval pass**: Use already-accumulated data to generate plots
- **Output**: 4 plot types × 3 representative layers = 12 plots per checkpoint
- **Storage**: ~450KB total per plot generation
- **Note**: plot_interval defaults to save_interval for convenience, but has nothing to do with checkpoint saving - it's just a larger number to avoid plotting too frequently

---

## Visualizations by Timing

### JSON Logging (every eval_interval ~500 steps)
*Low overhead, stored as JSON for structured logging*

#### 1. Expert Activation Distribution (Histogram)
- **Data**: Count of tokens using 0, 1, 2, 3, 4+ experts
- **Storage**: Time-series JSON array with counts and percentages
- **Per layer**: One histogram per layer
- **Format**: `expert_counts.json`
```json
[
  {
    "step": 500,
    "layer_0": {
      "0_experts": {"count": 523, "percent": 25.5},
      "1_experts": {"count": 892, "percent": 43.5},
      "2_experts": {"count": 421, "percent": 20.5},
      "3_experts": {"count": 164, "percent": 8.0},
      "4+_experts": {"count": 48, "percent": 2.3}
    },
    "layer_1": { ... }
  },
  {
    "step": 1000,
    "layer_0": { ... },
    "layer_1": { ... }
  }
]
```

#### 2. Router Weight Percentiles (CDF Summary)
- **Data**: Key percentiles of activation weights
- **Storage**: Time-series JSON array with percentiles (10th, 25th, 50th, 75th, 90th, 95th, 99th)
- **Per layer**: One summary per layer
- **Format**: `weight_percentiles.json`
```json
[
  {
    "step": 500,
    "layer_0": {
      "p10": 0.023, "p25": 0.081, "p50": 0.234,
      "p75": 0.512, "p90": 0.734, "p95": 0.823, "p99": 0.921
    },
    "layer_1": { ... }
  },
  {
    "step": 1000,
    "layer_0": { ... },
    "layer_1": { ... }
  }
]
```

### Plot Generation (every plot_interval ~5000 steps)
*Generate plots from accumulated exact statistics*

**Layer selection**: Every 4th layer + last (e.g., 24-layer model → {0, 4, 8, 12, 16, 20, 23})
**Memory**: Scales with depth (~2.7GB for 12 layers, ~4.7GB for 24 layers)

#### 1. Router Weight Distribution (Full CDF)
- **Purpose**: Complete view of weight distribution (not just percentiles)
- **Data needed**: All activation weights from routing
- **Plots**: One CDF curve per representative layer
- **X-axis**: Activation weight (0 to 1)
- **Y-axis**: Cumulative fraction of weights ≤ x
- **Details**: Smooth curve showing full distribution shape

#### 2. Expert Count vs Token Loss (Violin Plot)
- **Purpose**: Do tokens with more experts have higher/lower loss?
- **Data needed**: Per-token loss + fanout
- **Plots**: One violin plot per representative layer
- **X-axis**: # experts (0, 1, 2, 3, 4+)
- **Y-axis**: Token loss distribution

#### 3. Token Entropy vs Expert Count (Violin Plot)
- **Purpose**: Does prediction uncertainty correlate with expert activation?
- **Data needed**: Per-token entropy from output logits + fanout
- **Plots**: One violin plot per representative layer
- **X-axis**: # experts (0, 1, 2, 3, 4+)
- **Y-axis**: Token entropy distribution

#### 4. Expert Cutoff Distribution (Histogram) - DEPRECATED
- **Status**: Currently shows histogram of cutoff values, not meaningful
- **Original intent**: Per-expert cutoff vs avg loss scatter (unclear value)
- **Replacement**: Could track cutoff evolution over time in JSON logs if needed

---

## Directory Layout

```
{output_dir}/
├── eval_logs/
│   ├── expert_counts.json           # Time-series array: all steps, all layers
│   └── weight_percentiles.json      # Time-series array: all steps, all layers
└── visualizations/
    ├── step_5000/
    │   ├── weight_cdf/
    │   │   ├── layer_0.png
    │   │   ├── layer_12.png         # middle layer (assuming 24 layers)
    │   │   └── layer_23.png         # last layer
    │   ├── loss_by_experts/
    │   │   ├── layer_0_violin.png
    │   │   ├── layer_12_violin.png
    │   │   └── layer_23_violin.png
    │   └── entropy_vs_experts/
    │       ├── layer_0_violin.png
    │       ├── layer_12_violin.png
    │       └── layer_23_violin.png
    ├── step_10000/
    │   └── ... (same structure)
    └── step_15000/
        └── ... (same structure)
```

---

## Computational Considerations

**Key principle**: Collect **exact statistics** over full validation set (~100M tokens) by accumulating data during the existing eval pass.

### Memory Usage

Scales with model depth (every 4th layer + last). For ~100M tokens:

**12-layer model (4 tracked layers):**
- Router weights: 100M × 4 × 8 experts × 4 bytes ≈ 1.6GB
- Per-token data: 100M × 4 × 9 bytes ≈ 900MB
- **Total**: ~2.7GB

**24-layer model (7 tracked layers):**
- Router weights: 100M × 7 × 8 experts × 4 bytes ≈ 2.8GB
- Per-token data: 100M × 7 × 9 bytes ≈ 1.9GB
- **Total**: ~4.7GB

Formula: ~670MB × num_tracked_layers

### Compute Overhead

- **During validation iteration**: Append batch tensors to lists (minimal overhead)
- **After validation completes**:
  - JSON logging: Compute histograms and percentiles from accumulated data
  - Plot generation (when step % plot_interval == 0): Process accumulated data into visualizations
- **No extra validation passes**: Everything piggybacked on existing eval iteration

---

## Implementation Structure

### Code Architecture

**Module**: `src/visualizer.py`

```python
class EvalVisualizer:
    def __init__(self, config, output_dir):
        self.num_layers = config.model.num_layers
        self.output_dir = output_dir
        self.repr_layers = {0, num_layers // 2, num_layers - 1}
        self.accumulated_data = {}

    def accumulate_batch(self, batch_data, layer_idx):
        """Accumulate batch statistics during eval iteration.

        Called during validation loop for representative layers.
        Appends batch tensors to lists (no sampling).
        """
        if layer_idx not in self.accumulated_data:
            self.accumulated_data[layer_idx] = defaultdict(list)

        self.accumulated_data[layer_idx]['weights'].append(batch_data['weights'])
        self.accumulated_data[layer_idx]['fanout'].append(batch_data['fanout'])
        self.accumulated_data[layer_idx]['loss'].append(batch_data['loss'])
        self.accumulated_data[layer_idx]['entropy'].append(batch_data['entropy'])
        # ... etc

    def log_eval_stats(self, step):
        """Lightweight JSON logging (every eval_interval).

        Computes statistics from accumulated data and appends to JSON files.
        """
        for layer_idx in self.repr_layers:
            data = self.accumulated_data[layer_idx]

            # Concatenate accumulated batches
            all_weights = torch.cat(data['weights'])
            all_fanout = torch.cat(data['fanout'])

            # Expert activation histogram
            counts = compute_histogram(all_fanout)
            append_to_json('expert_counts.json', step, layer_idx, counts)

            # Router weight percentiles
            percentiles = torch.quantile(all_weights, [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
            append_to_json('weight_percentiles.json', step, layer_idx, percentiles)

    def create_plots(self, step):
        """Generate plots from accumulated data (when step % plot_interval == 0).

        Processes accumulated exact statistics into visualizations.
        """
        for layer_idx in self.repr_layers:
            data = self.accumulated_data[layer_idx]

            # Concatenate all batches for plotting
            all_weights = torch.cat(data['weights'])
            all_fanout = torch.cat(data['fanout'])
            all_loss = torch.cat(data['loss'])
            all_entropy = torch.cat(data['entropy'])

            # Generate 3 plot types
            self._plot_weight_cdf(all_weights, step, layer_idx)
            self._plot_loss_violin(all_fanout, all_loss, step, layer_idx)
            self._plot_entropy_violin(all_entropy, all_fanout, step, layer_idx)

    def clear_accumulated_data(self):
        """Reset accumulators (called at start of each eval)."""
        self.accumulated_data = {}
```

### Integration

**Trainer modifications**:
```python
class Trainer:
    def __init__(self, ...):
        if self.config.training.enable_visualizations:
            from .visualizer import EvalVisualizer
            self.visualizer = EvalVisualizer(config, output_dir)

    def evaluate(self, step):
        self.model.eval()

        # Clear accumulated data from previous eval
        if self.config.training.enable_visualizations:
            self.visualizer.clear_accumulated_data()

        # Validation iteration (existing)
        eval_metrics = {}
        with torch.no_grad():
            for _ in range(num_batches):
                input_ids, labels = self.data_loader.next_batch()
                output = self.model(input_ids, labels)

                # Accumulate eval metrics (existing)
                self._update_metrics(eval_metrics, ...)

                # NEW: Accumulate visualization data for representative layers
                if self.config.training.enable_visualizations:
                    for layer_idx in self.visualizer.repr_layers:
                        batch_data = self._extract_vis_data(output, layer_idx)
                        self.visualizer.accumulate_batch(batch_data, layer_idx)

        # After full validation pass:

        # ALWAYS: JSON logging (every eval_interval)
        if self.config.training.enable_visualizations:
            self.visualizer.log_eval_stats(step)

        # CONDITIONAL: Plot generation (every plot_interval)
        plot_interval = self.config.training.plot_interval or self.config.training.save_interval
        if self.config.training.enable_visualizations and step % plot_interval == 0:
            self.visualizer.create_plots(step)

        return eval_metrics
```

---

## Data Requirements

### Per-Token Information (accumulated for 3 representative layers)

Data extracted during forward pass and accumulated in lists:
- **fanout**: # experts activated per token (1 byte per token)
- **loss**: Per-token cross-entropy loss (4 bytes per token)
- **entropy**: Prediction uncertainty from output logits: `H = -sum(p * log(p))` (4 bytes per token)
- **weights**: Post-activation routing weights (4 bytes × E experts per token)

### Per-Expert Aggregates (batch-level tracking)

For each layer and expert (minimal storage):
- **cutoff**: Current EMA cutoff value (from model state, tracked per batch)
- **avg_loss**: Mean loss of tokens processed by expert 0 (online mean, negligible storage)
- **usage**: Fraction of tokens that activate each expert (can be computed from fanout data)

---

## Summary

### Configuration
- **Single flag**: `enable_visualizations: bool = True` (default on, minimal overhead)
- **plot_interval**: Controls plot generation frequency (defaults to `save_interval`)
  - Note: Has nothing to do with checkpoint saving - just a convenient large interval

### During Evaluation (every eval_interval ~500 steps)
- **Hook location**: Inside `Trainer.evaluate()` during existing validation iteration
- **Data accumulation**: Append batch tensors for 3 representative layers (~2GB total)
- **JSON logging**: Compute and append to time-series files after validation completes
  - Expert activation histogram → `expert_counts.json`
  - Router weight percentiles → `weight_percentiles.json`
- **Storage**: ~1-2KB per eval_interval
- **Overhead**: Minimal - just list appends during iteration

### Plot Generation (every plot_interval ~5000 steps)
- **Trigger**: When `step % plot_interval == 0` during evaluation
- **Data source**: Already-accumulated exact statistics (no extra pass!)
- **Layers**: Every 4th layer + last (scales with model depth)
- **Outputs**: 3 plot types per tracked layer:
  1. **Router weight CDF** (full distribution curve)
  2. **Loss by expert count** (violin) - Do more experts = harder tokens?
  3. **Entropy by expert count** (violin) - Does uncertainty drive activation?
  4. ~~Expert cutoff distribution~~ (deprecated - not meaningful)
- **Memory**: 2.7-6GB depending on model depth (accumulated during eval)
- **Storage**: Scales with depth (12 plots for 12-layer, 21 plots for 24-layer model)

### Key Design Decisions
- **Exact statistics**: No sampling, collect full data for tracked layers
- **No extra validation passes**: Piggyback on existing eval iteration
- **Every-4 layer pattern**: Uniform coverage across depth, scales naturally with model size
- **Two-level granularity**: JSON percentiles every eval_interval, full plots every plot_interval

---

## Future: Domain-Specific Token Examples (Separate Infrastructure)

### Overview
Qualitative analysis showing actual token sequences with their routing patterns across different domains. Requires domain-labeled datasets and separate evaluation infrastructure.

### Purpose
Understand if routing patterns correlate with:
- Domain type (code, math, prose, dialogue)
- Linguistic properties (syntax, semantics, pragmatics)
- Task difficulty (factual recall vs reasoning)

### Visualization Design

**Format**: Interactive table or grid showing:
- **Token sequence** (context window of ~50 tokens)
- **Per-token expert activation** (heatmap: rows = layers, columns = tokens)
- **Expert IDs** that activated for each token
- **Domain label** and **difficulty score** (if available)

**Selection criteria**:
- High-fanout tokens (4+ experts consistently)
- Low-fanout tokens (0-1 experts consistently)
- Domain transitions (where domain changes mid-sequence)
- High-loss tokens (model struggled)
- Low-loss tokens (model confident)

### Example Output

```
Domain: Code (Python)
Difficulty: Medium
Tokens: [50 tokens showing a function definition]

Layer 0: ████░░░░████░░░░░░░░░████████░░░░░░░░░░████░░░░░░
Layer 1: ░░████░░░░░░████████░░░░░░████░░░░████░░░░████░░░
Layer 2: ██░░░░████░░░░░░░░████░░░░░░░░████░░░░░░░░░░████
...

Token 15: "def" → Experts [0, 3, 7] (3 experts)
Token 16: "calculate" → Experts [1, 4] (2 experts)
Token 17: "(" → Experts [2] (1 expert)
...
```

### Data Requirements

**Domain-labeled datasets**:
- Code: The Stack, GitHub code
- Math: MATH dataset, GSM8K
- Prose: Books corpus, news articles
- Dialogue: Reddit, conversational data

**Infrastructure needs**:
- Separate eval script with domain-aware data loading
- Token-level routing capture (already needed for save_step)
- HTML/interactive visualization generator (not just PNG)

### Implementation Notes

**Not part of main training loop**:
- Run separately on validation sets post-training
- Or during dedicated analysis checkpoints
- Too heavy for regular eval_step/save_step

**Storage**:
- HTML files with embedded data
- Or JSON + separate viewer tool
- ~1-10MB per domain analysis

### When to Build This
- After base visualization system is working
- When we have domain-labeled eval sets
- When qualitative analysis is needed for paper/debugging