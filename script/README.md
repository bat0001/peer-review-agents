# Scripts

## Kept Scripts

- `train.sh`: main training launcher (Hydra overrides + naming + EP toggle)
- `run_configs.sh`: run catalog; contains concrete experiment commands that call `train.sh`
- `download_data.sh`: downloads FineWeb-Edu parquet shards via in-repo code
- `train_tokenizer.sh`: trains RustBPE tokenizer via in-repo code

## Required Environment Variables

`train.sh` reads:

- `MODEL_SIZE` (required)
- `TRAINING_TOKENS` (required)
- `N_GPUS` (optional, default `1`)
- `MICRO_BATCH_SIZE` (optional)

## Typical Usage

```bash
# single run
MODEL_SIZE=tiny TRAINING_TOKENS=1 N_GPUS=1 ./script/train.sh --mlp expert_choice --g 2 --e 8

# run catalog
./script/run_configs.sh

# data + tokenizer
./script/download_data.sh -1 8
./script/train_tokenizer.sh 65536 2000000000
```
