# Plan: Routing Stability Analysis Across GEC, EC, and TC

## Summary

Implement a local-checkpoint-first analysis pipeline that quantifies routing stability across training checkpoints for `gec_shared`/`ec_shared`/`tc_shared` runs. The pipeline must produce comparable stability metrics across routing families, detect pathological "stable-but-collapsed" behavior, and output publication-ready figures and machine-readable tables.

Primary question:
- How stable are routing assignments checkpoint-to-checkpoint in GEC vs EC vs TC, and when does stability correlate with better model quality?

## Scope

In scope:
- New analysis entrypoint and Hydra config.
- Local checkpoint loading and fixed-eval-batch routing extraction.
- Cross-checkpoint stability metrics and summary aggregates.
- Visualization suite (core + diagnostics + advanced).
- Tests for metric correctness and determinism.

Out of scope:
- New router training methods.
- W&B-first data plumbing (optional adapters can be added later).
- Any change to training runtime behavior.

## Success Criteria

1. Analysis runs offline from local run directories with intermediate checkpoints.
2. For each run family (GEC/EC/TC), the tool outputs:
   - pairwise checkpoint stability matrix,
   - layer-wise stability trends,
   - aggregate stability summaries.
3. Tool marks degenerate routing cases separately from healthy stability.
4. Figures and CSV/Parquet outputs are reproducible with fixed seed + fixed eval batches.

## Required Inputs and Defaults

Data source defaults:
- Checkpoints under `outputs/<run>/<run>/checkpoints/checkpoint_step_*.pt`.
- Optional per-run training metrics from `metrics.jsonl` for alignment overlays.

Model family comparison defaults:
- `gec_shared` + `ec_shared` + `tc_shared` (recommended comparison set).

Checkpoint schedule defaults:
- Adjacent pairs (`t` vs `t+1` in selected list).
- Fixed-gap pairs (`t` vs `t+delta_steps`) with configurable deltas.

Evaluation data defaults:
- Fixed held-out token batches sampled once and reused across all checkpoints and families.

## Planned Public Interfaces

### 1) New Hydra analysis config

Add `configs/analysis/routing_stability.yaml`:

- `analysis.name`: output folder label.
- `analysis.runs`: list of run specs with:
  - `name`
  - `family` (`gec`, `ec`, `tc`)
  - `checkpoint_dir`
- `analysis.ckpt_select`:
  - `mode`: `all`, `stride`, `explicit_steps`
  - `stride`: int (used when `mode=stride`)
  - `steps`: list[int] (used when `mode=explicit_steps`)
- `analysis.pairs`:
  - `include_adjacent`: bool
  - `fixed_gaps`: list[int]
- `analysis.eval_data`:
  - `source`: `fineweb_eval_bundle` or `text_file`
  - `n_batches`
  - `batch_size`
  - `seq_len`
  - `seed`
- `analysis.layers`:
  - `mode`: `all` or `representative`
  - `representative`: default `[0, 1, n/4, n/2, 3n/4, n-1]`
- `analysis.output_dir`: default `outputs/analysis/routing_stability/${analysis.name}`

### 2) New analysis entrypoint

Add top-level script:
- `routing_stability.py`

Behavior:
- Loads checkpoints per run.
- Builds routing assignment tensors on shared eval batches.
- Computes pairwise stability metrics.
- Writes artifacts (tables + plots + markdown summary).

### 3) Proposed output schema

Files per analysis run:
- `pair_metrics.csv`: one row per `(run, layer, ckpt_a, ckpt_b, metric_name, metric_value)`.
- `aggregate_metrics.csv`: per-run/per-layer aggregates.
- `pair_matrix_<run>_<layer>.csv`: square pairwise matrix for heatmap.
- `summary.md`: concise narrative with key findings and warnings.
- `fig_*.png`: generated visualizations.

## Comparable Routing Representation

To compare families consistently:

Base representation:
- Binary assignment tensor `A[layer, token, expert] in {0,1}` on the same eval tokens.

Family mapping:
- GEC/EC: use routed expert selections from expert-choice mask.
- TC: convert top-k token-choice selections to equivalent binary mask.
- Shared expert:
  - Exclude from primary cross-family stability metric.
  - Report shared-expert stability as supplemental metric for shared variants.

## Metrics (Decision Complete)

Primary metrics:
1. Binary mask correlation (Pearson and Spearman on flattened `A`).
2. Jaccard overlap on active token-expert edges.
3. Per-token top-set overlap (intersection over union of expert sets).
4. Per-expert token-set overlap (expert-centric Jaccard).
5. Usage-distribution divergence across checkpoints (JS divergence).
6. Expert-rank stability (Kendall tau on expert usage ranking).

Secondary metrics:
1. Churn rate: fraction of edges that changed state between checkpoints.
2. Persistent-edge ratio over K checkpoints.
3. Stability normalized by checkpoint loss delta.

Degeneracy guards:
- If mean edge density < epsilon or > 1 - epsilon, tag as "degenerate routing".
- If usage Gini > threshold and entropy < threshold while stability is high, tag as "stable but collapsed".

## Visualization Plan (Expanded Brainstorm)

Core (must implement first):
1. Checkpoint-pair correlation heatmap (`ckpt_i x ckpt_j`).
2. Stability-vs-training-step line plot per family.
3. Layer-by-layer small multiples (one panel per representative layer).
4. Stability vs eval loss scatter (color by family, point size by step gap).

Diagnostics (must implement):
1. Churn-rate timeline with collapse tags.
2. Usage entropy/Gini vs stability phase plot.
3. Stability decomposition bars:
   - token-set overlap,
   - expert-rank stability,
   - usage-distribution similarity.

Advanced brainstorm (implement if time permits):
1. Alluvial flow for token assignment transitions (`t -> t+delta`).
2. Survival curve of edge persistence across checkpoint windows.
3. Stability-lag spectrum: stability as function of step gap.
4. Cohort plots:
   - easy/medium/hard token cohorts (by token loss quantile),
   - per-cohort stability differences.
5. Expert "fingerprint drift" map:
   - per-expert centroid cosine shift over time.
6. Transition graph:
   - nodes are experts, edge weight is token migration between experts.
7. Stability control chart:
   - moving average + confidence bands to spot instability bursts.
8. Layer radar chart:
   - multi-metric stability signature per family.
9. Regime map:
   - x=`cutoff_abs_deviation`, y=stability, color=loss trend.
10. Sankey at selected milestones (early/mid/late training).

Presentation rules:
- Use consistent color family mapping (`GEC`, `EC`, `TC`).
- Annotate major LR schedule phase boundaries when available.
- Always pair "stability" with at least one health metric to avoid false interpretation.

## Implementation Steps

1. Scaffold config and script entrypoint.
2. Add checkpoint discovery and consistent step sorting.
3. Reuse existing checkpoint loading path from current eval/analysis utilities.
4. Build deterministic eval batch sampler and cached token batches.
5. Extract routing masks per layer/expert for each checkpoint.
6. Compute pairwise metrics and aggregate summaries.
7. Generate required figures and markdown summary.
8. Add tests and run local validation on one run from each family.

## Testing Plan

Unit tests:
- Metric sanity on synthetic masks:
  - identity pair gives perfect similarity,
  - disjoint masks give near-zero overlap.
- Degeneracy detector test cases:
  - all-zero/all-one masks,
  - high-concentration collapse pattern.

Integration tests:
- End-to-end on small checkpoints (tiny/d8) with 2-3 checkpoint pairs.
- Determinism check with fixed seed.
- Missing checkpoint handling test (non-contiguous steps).

Acceptance checks:
- Outputs created with expected schema.
- Summary includes:
  - top stable run/layer,
  - most unstable run/layer,
  - any collapse warnings.

## Risks and Mitigations

Risk: family-specific routing outputs differ in shape/semantics.
- Mitigation: enforce single normalized binary tensor contract before metric computation.

Risk: long runtime for pairwise all-to-all checkpoints.
- Mitigation: support step stride and fixed-gap subsets; cache per-checkpoint routing tensors.

Risk: misreading high stability as success.
- Mitigation: include health metrics (entropy/Gini/churn) and explicit warning labels.

## Assumptions

- Intermediate checkpoints are available locally.
- Checkpoints include enough state to reconstruct routing at inference/eval.
- `NANOCHAT_BASE_DIR` and tokenizer paths are valid for eval batch creation.
- Shared expert is excluded from primary cross-family comparability by default.

