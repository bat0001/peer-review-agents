# CORE Eval Batched Prefill Validation (2026-02-11)

## Summary

Validated the model-owned eval batch path and CORE batched prefills on 2 GPUs with EP checkpoint.
Run completed successfully and produced CORE metric output.

## Environment

- GPUs used: `CUDA_VISIBLE_DEVICES=2,3`
- Launcher: `torchrun --nproc_per_node=2`
- Python: `/data2/hanchi/miniconda3/envs/nanochat/bin/python`

## Checkpoint

- Input checkpoint:
  - `outputs/gec_shared_d8_G2E8_0.01B_ep8/gec_shared_d8_G2E8_0.01B_ep8/checkpoints/checkpoint_step_100.pt`
- Repaired checkpoint used for eval:
  - `outputs/gec_shared_d8_G2E8_0.01B_ep8/gec_shared_d8_G2E8_0.01B_ep8/checkpoints/checkpoint_step_100_fixed.pt`

## Command (successful run)

```bash
CUDA_VISIBLE_DEVICES=2,3 /data2/hanchi/miniconda3/envs/nanochat/bin/torchrun --nproc_per_node=2 eval_core.py \
  eval.core_checkpoint_path=outputs/gec_shared_d8_G2E8_0.01B_ep8/gec_shared_d8_G2E8_0.01B_ep8/checkpoints/checkpoint_step_100_fixed.pt \
  eval.core_metric_max_per_task=64 \
  eval.core_eval_examples_per_forward=4
```

## Result

- CORE metric: `-0.022338`

Selected task outputs from rank0:
- `hellaswag_zeroshot acc=0.187500 centered=-0.083333`
- `arc_easy acc=0.375000 centered=0.166667`
- `copa acc=0.531250 centered=0.062500`
- `winograd acc=0.531250 centered=0.062500`

## Notes

- Attempt with `eval.core_metric_max_per_task=8` failed on few-shot sampling size constraints.
- Using `64` avoided the small-population sampling failure and completed end-to-end.
