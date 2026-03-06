# Expert Threshold (ET)

Standalone training repo for dense, EC, ET, and token-choice (ScatterMoE) GPT-style models.

## What Is Included

- Training entrypoint: `train.py`
- Core model/runtime code: `src/`
- Hydra configs: `configs/`
- Minimal scripts: `script/train.sh`, `script/run_configs.sh`, `script/download_data.sh`, `script/train_tokenizer.sh`
- CORE evaluation: `eval_core.py` and `src/eval/core.py`
- Wandb logging support

This release intentionally excludes benchmark suites, visualization modules, agent/memory files, and archived/reference repos.

## Requirements

- Python 3.10+
- CUDA-capable PyTorch environment
- `NANOCHAT_BASE_DIR` environment variable set

Example:

```bash
export NANOCHAT_BASE_DIR=/data2/.cache/nanochat
pip install -r requirements.txt
```

## Data And Tokenizer (Integrated, No External nanochat Repo)

Download parquet shards:

```bash
./script/download_data.sh -1 8
```

Train tokenizer from local parquet data:

```bash
./script/train_tokenizer.sh 65536 2000000000
```

Both scripts use in-repo modules (`src.data.nanochat_dataset`, `src.data.train_tokenizer`).

## Train

Quick single-process EC run:

```bash
MODEL_SIZE=tiny TRAINING_TOKENS=1 N_GPUS=1 ./script/train.sh --mlp ec --g 2 --e 8
```

Threshold-oriented ET run with implied EC warmup:

```bash
MODEL_SIZE=tiny TRAINING_TOKENS=10 N_GPUS=1 ./script/train.sh --mlp et --g 2 --e 8
```

Run catalog (multiple experiments):

```bash
./script/run_configs.sh
```

You can also call Hydra directly:

```bash
python train.py model_size=tiny mlp=ec
python train.py model_size=tiny mlp=et
```

## CORE Eval

```bash
python eval_core.py eval.core_checkpoint_path=/path/to/checkpoint.pt
```

## Engine Design

Two expert engines are kept intentionally:

- `ExpertEngine` (`src/models/engines/engine.py`): default routed-expert path
- `ParallelExperts` (`src/models/engines/parallel_experts_manual.py`): expert-parallel path

Wrappers select by `model.expert_parallel`.

## Provenance Notes

- Training/data/tokenizer flow is adapted from nanochat-style recipes and integrated directly into this repo.
- Token-choice kernels/operators are sourced from vendored ScatterMoE code under `scattermoe/`.
- File-level provenance comments are included in runtime modules.
