# Scripts

## Architecture

```
SLURM Scripts (3rd tier)      → Set hardware: N_GPUS, MODEL_SIZE, TRAINING_TOKENS, MICRO_BATCH_SIZE
    ↓
run_configs.sh (2nd tier)     → Clean experiment catalog, calls train.sh with args
    ↓
train.sh (1st tier)           → Arg parsing, defaults, auto-enable features, name building
    ↓
train.py                      → Hydra config
```

## train.sh

Core training launcher. Accepts named arguments and reads hardware config from environment.

### Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--mlp` | MLP type (required) | `dense`, `gec_shared`, `tc`, `tc_shared` |
| `--g` | Granularity (MoE only) | `2` |
| `--e` | Expansion (MoE only) | `8` |
| `--capacity` | Expert capacity factor | `0.25` |
| `--warmup` | Threshold routing switch step | `0`, `1000` |
| `--ema-start` | Cutoff EMA update start step | `0`, `200` |
| `--load-balance` | Load balance method | `deepseek`, `aux` |
| `--deepseek-lr` | DeepSeek bias learning rate | `0.001` |
| `--aux-coef` | Aux loss coefficient | `0.01` |
| `--router` | Router activation | `softmax` |
| `--norm` | Normalization mode | `sum` |
| `--cutoff-alpha` | Cutoff EMA alpha | `0.999` |
| `--batch-size` | Total batch size override | `262144` |
| `--name` | Custom experiment name | `my_experiment` |

### Environment Variables (from SLURM)

| Variable | Description |
|----------|-------------|
| `N_GPUS` | Number of GPUs (default: 1) |
| `MODEL_SIZE` | Model size (required) |
| `TRAINING_TOKENS` | Training tokens in billions (required) |
| `MICRO_BATCH_SIZE` | Per-device batch size |

### Auto-Enable Features

- **Threshold routing**: Setting `--capacity` automatically enables threshold routing (`--warmup 0`)
- **Two-gate schedule**: `--warmup` controls topk→threshold switch; `--ema-start` controls when cutoff EMA updates begin.

### Experiment Naming

Names are auto-generated to capture all config variations:
- `dense_d12_30B` - dense baseline
- `gec_shared_d12_G2E8_30B` - GEC shared
- `gec_shared_d12_G2E8_30B_cap0.25_warmup0` - GEC with capacity
- `gec_shared_d12_G2E8_30B_cap0.5_warmup200_ema200_alpha0.999_ep8` - split-gate threshold run
- `tc_shared_d12_G2E8_30B_deepseek_dslr0.001` - TC with DeepSeek

## run_configs.sh

Experiment catalog. Each line is a self-contained experiment:

```bash
./script/train.sh --mlp dense
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999
./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.001
```

## SLURM Scripts

### quick_train.slurm
Quick testing on 2 GPUs with 5B tokens.

### run_train.slurm
Full training on 8 GPUs with 30B tokens.

### expert_specialization_eval.slurm
1-GPU analysis job: installs `datasets` if missing, prefetches GSM8K + HumanEval,
and runs `expert_specialization` for the configured run list.

### debug_a5000.sh
Local debug script for A5000 server (0.01B tokens, 2 GPUs).
