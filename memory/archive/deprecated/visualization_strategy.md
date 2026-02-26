# Visualization Strategy

## Philosophy

**Static behavior analysis during evaluation** - Understand expert routing patterns by analyzing aggregate statistics over the full validation set. Track trends over training via periodic snapshots during eval.

**Two-level granularity**:
- **JSON logs** (every eval_interval): Lightweight time-series for tracking trends
- **Plots** (every plot_interval): Full visualizations for deep analysis

**Exact statistics** - Collect complete data for representative layers (~2GB) to get precise distributions. No sampling approximations.

**Zero-cost piggybacking** - Reuse existing evaluation iteration. No extra forward passes.

## Core Principles

### What to Measure

**Router behavior**:
- How are routing weights distributed? (CDF)
- What percentiles matter for capacity planning? (JSON percentiles)

**Expert activation patterns**:
- How many experts activate per token? (histogram)
- Does this vary by layer? (representative layers)

**Routing correlations**:
- Do harder tokens (high loss) use more/fewer experts? (violin)
- Does uncertainty (entropy) drive more activation? (violin)

### What NOT to Measure

- ❌ Training-time dynamics (keep training fast)
- ❌ Per-expert detailed analysis (focus on aggregate patterns)
- ❌ All layers (representative layers sufficient)
- ❌ Cutoff evolution tracking (unclear value, deprecated)

## Implementation Constraints

### Representative Layers Only
- Process every 4th layer + last layer (e.g., {0, 4, 8, 12, 16, 20, 23} for 24-layer model)
- Scales naturally with model depth while maintaining reasonable memory
- Full per-layer scalar metrics still logged via `routing_metrics.py`

### Memory Budget
Scales with model depth. For ~100M validation tokens:

| Model Depth | Layers Tracked | Memory |
|-------------|----------------|--------|
| 2 layers | {0, 1} (2) | ~1.3GB |
| 12 layers | {0, 4, 8, 11} (4) | ~2.7GB |
| 24 layers | {0, 4, 8, 12, 16, 20, 23} (7) | ~4.7GB |
| 32 layers | {0, 4, 8, 12, 16, 20, 24, 28, 31} (9) | ~6GB |

Formula: ~670MB × num_tracked_layers

### Configuration
- `enable_visualizations: bool = True` (single flag, default on)
- `plot_interval`: Defaults to `save_interval` (convenient large interval)

## Output Format

### JSON Logs (every eval_interval ~500 steps)
Time-series tracking for trend analysis:

1. **Expert activation histogram** (`expert_counts.json`)
   - Token counts by fanout: 0, 1, 2, 3, 4+ experts
   - Per representative layer, with percentages

2. **Router weight percentiles** (`weight_percentiles.json`)
   - p10, p25, p50, p75, p90, p95, p99
   - Per representative layer

### Plots (every plot_interval ~5000 steps)
Full distributions from exact statistics:

1. **Router weight CDF** (`weight_cdf/`)
   - X: router weight value, Y: cumulative probability
   - Shows full distribution shape (not just percentiles)

2. **Loss by expert count** (`loss_by_experts/`)
   - X: # experts (0, 1, 2, 3, 4+), Y: loss distribution (violin)
   - Answers: Do harder tokens activate more/fewer experts?

3. **Entropy by expert count** (`entropy_vs_experts/`)
   - X: # experts (0, 1, 2, 3, 4+), Y: entropy distribution (violin)
   - Answers: Does prediction uncertainty drive more activation?

4. ~~Cutoff distribution~~ (deprecated - not meaningful)

## Directory Structure

```
{output_dir}/
├── eval_logs/
│   ├── expert_counts.json
│   └── weight_percentiles.json
└── visualizations/
    ├── step_5000/
    │   ├── weight_cdf/layer_{0,4,8,12,16,20,23}.png
    │   ├── loss_by_experts/layer_{0,4,8,12,16,20,23}_violin.png
    │   └── entropy_vs_experts/layer_{0,4,8,12,16,20,23}_violin.png
    └── step_10000/...
```
(Example for 24-layer model)

## Design Rationale

**Why exact statistics vs sampling?**
- 2GB memory is acceptable for precise distributions
- Avoids sampling bias in tail behavior
- Percentiles and CDFs require full data anyway

**Why every-4 pattern vs all layers?**
- Reasonable memory: 2-6GB for typical models (vs 16-21GB for all layers)
- Uniform coverage across depth captures routing evolution
- Granular enough to detect layer-specific patterns
- Scalar metrics (mean, std) still tracked for all layers via routing_metrics.py

**Why separate JSON logs and plots?**
- JSON: lightweight, structured, easy to parse for trends
- Plots: expensive to generate, for deep inspection only
- Different update frequencies optimize cost/value tradeoff

**Why no training-time collection?**
- Keep training loop fast (inner loop is critical path)
- Eval statistics on fixed dataset more interpretable
- Routing behavior more stable during eval (no dropout/gradient noise)
