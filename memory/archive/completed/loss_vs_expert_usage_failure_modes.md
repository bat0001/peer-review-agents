# Plan: Loss vs Expert Usage Failure Mode Analysis

## Archive Status (2026-02-25)

- Archived from `memory/plans/` after implementation direction changed.
- Original plan targeted offline `metrics.jsonl` failure-mode mining.
- Implemented path uses token-level eval instrumentation in `eval_moe_visualization.py` (single-pass checkpoint eval) and is documented in `memory/archive/completed/eval_moe_visualization.md`.
- Kept for historical context and alternative future analysis direction.

## Summary

Implement an analysis pipeline that aligns training/eval loss signals with routing usage dynamics to detect failure modes and explain when routing behavior helps or hurts optimization and generalization.

Primary question:
- Which expert-usage patterns predict loss spikes, stagnation, or downstream degradation, and do those patterns differ across GEC, EC, and TC?

## Scope

In scope:
- Time-series alignment of loss and routing metrics from local logs.
- Failure mode detection rules and event extraction.
- Lag/correlation analysis between routing signals and loss.
- Visualization outputs for diagnosis and paper figures.

Out of scope:
- Modifying training code or router algorithm.
- Introducing online monitoring infrastructure.

## Success Criteria

1. Offline tool ingests local `metrics.jsonl` from multiple runs.
2. Produces a unified analysis table with synchronized per-step metrics.
3. Detects and logs failure events with explicit rule triggers.
4. Generates plots that make failure signatures interpretable and comparable across families.

## Required Inputs and Defaults

Default source:
- Local `outputs/<run>/<run>/metrics.jsonl`.

Optional source:
- Checkpoint-derived supplements (if some routing fields are absent in logs).

Required fields (at least one in each category):
- Loss:
  - `loss` and/or `train_loss_ema`.
  - optional eval/core metrics when available.
- Usage/routing:
  - `expert_usage`
  - `avg_experts_per_token`
  - `tokens_with_no_expert`
  - `cutoff_abs_deviation` (if EC/GEC family)
  - capacity metrics (`capacity_overflow_rate`, `capacity_underflow_rate`) when present.

## Planned Public Interfaces

### 1) New Hydra analysis config

Add `configs/analysis/loss_usage.yaml`:

- `analysis.name`
- `analysis.runs`:
  - `name`
  - `family`
  - `metrics_path`
- `analysis.align`:
  - `step_field` (default `step`)
  - `smoothing_window`
  - `resample_stride`
- `analysis.features`:
  - usage concentration metric (`gini` or `entropy`, default both)
  - moving statistics windows
- `analysis.failure_rules` thresholds:
  - collapse concentration threshold
  - no-expert threshold
  - overflow/underflow persistence windows
  - cutoff lag threshold
- `analysis.output_dir`: default `outputs/analysis/loss_usage/${analysis.name}`

### 2) New analysis entrypoint

Add top-level script:
- `analysis_loss_usage.py`

Behavior:
- Parse runs and load metrics lines.
- Flatten list-valued routing arrays into derived scalars.
- Align time-series and compute lagged relationships.
- Apply failure rule engine and emit event tables + figures.

### 3) Proposed output schema

- `joined_timeseries.parquet`: aligned step-wise metrics and derived features.
- `failure_events.csv`: one row per detected event with rule name and interval.
- `lag_correlation.csv`: lag-indexed correlations for selected feature/loss pairs.
- `report.md`: summarized findings and recommended follow-up experiments.
- `fig_*.png`: visual diagnostics.

## Derived Features

Per-step derived metrics:
1. Usage entropy (routed experts only).
2. Usage Gini coefficient.
3. Top-expert share and top-2 share.
4. Usage variance and coefficient of variation.
5. Churn proxy from representative metrics when direct mask churn is unavailable.
6. Capacity pressure score:
   - weighted combination of overflow + underflow.
7. EMA lag proxy from `cutoff_abs_deviation` (EC/GEC).

Optional derived metrics (when eval/core exists):
1. Generalization gap proxy:
   - `eval_loss - train_loss_ema`.
2. CORE-vs-routing relationship windows.

## Failure Modes (Decision Complete Rules)

1. Collapse mode:
   - Trigger when usage concentration exceeds threshold for `N` consecutive steps.
   - Confirm with low entropy and weak/negative loss improvement slope.

2. Starvation mode:
   - Trigger when `tokens_with_no_expert` or underflow stays above threshold.
   - Confirm with worsened loss trend over same window.

3. Saturation/overflow mode:
   - Trigger when overflow is persistently high.
   - Confirm with unstable loss or noisy convergence.

4. EMA lag mode (GEC/EC):
   - Trigger when `cutoff_abs_deviation` remains high for `N` steps.
   - Confirm with rise in routing instability proxies and loss spikes.

5. Over-flattened routing mode:
   - Trigger when usage too uniform with low specialization indicators.
   - Confirm with underwhelming downstream gains despite stable train loss.

Event schema:
- `run`, `family`, `mode`, `start_step`, `end_step`, `duration`, `severity`, `trigger_metrics`.

## Visualization Plan

Required:
1. Dual-axis timeline: loss + usage concentration.
2. Event-annotated training curve with shaded failure intervals.
3. Scatter/hexbin: loss vs usage entropy/Gini.
4. Lag-correlation ribbon plot (feature leads/lags vs loss).
5. Family-faceted comparison panels (GEC/EC/TC).

Recommended additions:
1. Regime segmentation view:
   - early training, mid training, LR decay.
2. Heatmap of pairwise metric correlations over rolling windows.
3. Step-window boxplots of concentration metrics pre/post event.
4. "Traffic-light" dashboard:
   - green/yellow/red per failure mode across timeline.
5. Cohort analysis by layer representative metrics when available.

## Implementation Steps

1. Add config and entrypoint.
2. Build robust parser for heterogeneous `metrics.jsonl` schema across families.
3. Implement feature engineering and smoothing options.
4. Add failure rule engine with explicit thresholds from config.
5. Compute lag/cross-correlation tables.
6. Generate figures and markdown report.
7. Validate on at least one run from each family.

## Testing Plan

Unit tests:
- Usage concentration/entropy/Gini correctness on synthetic vectors.
- Failure-rule trigger tests with synthetic timeseries.
- Lag-correlation indexing tests.

Integration tests:
- Parse and align real local `metrics.jsonl` from:
  - one `gec_shared` run,
  - one `ec_shared` run,
  - one `tc_shared` run.
- Ensure outputs are generated even when some optional metrics are missing.

Acceptance checks:
- `failure_events.csv` populated with reproducible intervals.
- `joined_timeseries.parquet` contains all derived fields documented in report.
- `report.md` includes:
  - dominant failure mode per run,
  - strongest leading indicator feature,
  - suggested experimental follow-up.

## Risks and Mitigations

Risk: schema drift between older/newer runs.
- Mitigation: explicit field mapping layer and graceful missing-field handling.

Risk: spurious correlations due to non-stationarity.
- Mitigation: use rolling windows, regime-aware analysis, and event-based confirmation rules.

Risk: overfitting thresholds to a single run.
- Mitigation: keep thresholds configurable and report sensitivity checks.

## Assumptions

- Local run metrics exist and are readable.
- Step indices are monotonic per run (or can be sorted safely).
- Loss and routing metrics share compatible logging cadence or can be resampled.
- Cross-family comparison uses normalized derived metrics, not raw scale equality.
