# Configs

Hydra config tree for training/eval.

## Layout

- `config.yaml`: base defaults
- `model_size/`: model scale presets
- `mlp/`: architecture type (`dense`, `ec`, `et`, `token_choice`)
- `optimizer/`: optimizer presets
- `training/`: training schedule presets
- `experiment/`: small override bundles (for example `debug`)
- `eval/`: CORE eval defaults
- `presets/`: fully specified runnable presets

## Basic Commands

```bash
# defaults
python train.py

# explicit groups
python train.py model_size=tiny mlp=ec
python train.py model_size=tiny mlp=et

# with experiment override
python train.py +experiment=debug

# preset
python train.py --config-name=presets/ec_tiny
python train.py --config-name=presets/et_tiny
```

## Override Rules

- Structured configs are enabled; override existing keys directly.
- New keys require `+key=value`.
- `training.max_steps` is defined in `training/standard.yaml`, so use:

```bash
python train.py training.max_steps=100
```

## Fast E2E Debug Commands

```bash
# 1) tiny training run, save checkpoints quickly, no wandb
CUDA_VISIBLE_DEVICES=0 python train.py \
  model_size=micro mlp=dense \
  training.max_steps=2 training.save_interval=1 \
  training.eval_interval=999999 eval.core_metric_every=0 \
  training.compile_model=false \
  training.per_device_batch_size=1 training.total_batch_size=2048 \
  experiment_name=e2e_debug_nowandb \
  output_dir=/data2/hanchi/Global-Expert-Choice/outputs/e2e_debug_nowandb \
  logging.use_wandb=false

# 2) standalone CORE eval from checkpoint
CUDA_VISIBLE_DEVICES=0 python eval_core.py \
  eval.core_checkpoint_path=/data2/hanchi/Global-Expert-Choice/outputs/e2e_debug_nowandb/checkpoints/checkpoint_step_2.pt \
  eval.core_metric_max_per_task=2 \
  eval.core_eval_examples_per_forward=2

# 3) wandb path validation (offline mode)
WANDB_MODE=offline CUDA_VISIBLE_DEVICES=0 python train.py \
  model_size=micro mlp=dense \
  training.max_steps=2 training.save_interval=1 \
  training.eval_interval=999999 eval.core_metric_every=0 \
  training.compile_model=false \
  training.per_device_batch_size=1 training.total_batch_size=2048 \
  logging.use_wandb=true logging.log_interval=1 \
  experiment_name=e2e_debug_wandb_offline \
  output_dir=/data2/hanchi/Global-Expert-Choice/outputs/e2e_debug_wandb_offline
```

## Notes

- `NANOCHAT_BASE_DIR` must be set.
- `data.data_path` defaults to `${oc.env:NANOCHAT_BASE_DIR}/base_data`.
- `data.tokenizer_dir` defaults to `${oc.env:NANOCHAT_BASE_DIR}/tokenizer`.
- For shared servers, check `nvidia-smi` and pin a free GPU with `CUDA_VISIBLE_DEVICES`.
- `et` uses EC top-k warmup before switching to threshold routing by default.
