# Completed: MoE Eval Visualization Unification (Token-Level)

## Date
- 2026-02-25

## Summary
Implemented a unified evaluation visualization script that combines:
1. Router-logit histograms (existing behavior retained)
2. Token-level `loss vs fanout` analysis
3. `fanout vs position` analysis for long-context runs (e.g., 2k)
4. Correlation outputs including per-layer `R^2(fanout, token_nll)` and global `R^2(total_fanout, token_nll)`

## Script Renames (Generalized Naming)
- `eval_routing_logit_hist.py` -> `eval_moe_visualization.py`
- `script/eval_routing_logit_hist.slurm` -> `script/eval_moe_visualization.slurm`

SLURM updates:
- job name/log labels renamed to `moe-visualization`
- launcher now calls `eval_moe_visualization.py`
- experiment name prefix now `moe_visualization_<alias>`

## Output Artifacts
Under `outputs/<experiment>/eval_logs/routing_logit_hist/`:
- existing: `routing_logits_hist_*.png`, `routing_logits_hist_stats.json`
- added: `loss_vs_fanout_by_layer.{png,csv,json}`
- added: `fanout_vs_position.{png}`
- added: `fanout_vs_position_by_layer.csv`
- added: `fanout_vs_position_global.csv`
- added: `loss_fanout_correlation.{csv,json}`

## Implementation Notes
- Token loss is computed as per-token next-token NLL (`reduction='none'`) with last-token masking.
- Fanout is computed per layer using threshold mask `router_logit >= cutoff_ema`.
- Position axis uses absolute indices.
- `total_fanout` is defined per token as the sum of fanout across analyzed MoE layers.

## Validation Performed
- GPU availability checked with `nvidia-smi` before test runs.
- Smoke runs succeeded on local A5000 for:
  - short run (`sequence_length=256`)
  - 2k context run (`sequence_length=2048`)
- 2k run verified `fanout_vs_position` global length = 2048.

## Remote/B200 Update Note
- The renamed SLURM launcher is aligned with HiPerGator/B200 environment conventions (paths and env vars under `/orange/yonghui.wu/hanchi/...`).
- This document records that remote updates and naming cleanup were coordinated after B200-side usage feedback.

## Follow-up
- If additional cross-family stability work proceeds, continue using `memory/plans/routing_stability_gec_tc_ec.md` as the active plan.
