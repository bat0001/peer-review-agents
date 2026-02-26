# Configs

Hydra config tree for training/eval.

## Layout

- `config.yaml`: base defaults
- `model_size/`: model scale presets
- `mlp/`: architecture type (`dense`, `gec`, `gec_shared`, `ec`, `scattermoe_tc`, `tc_shared`)
- `optimizer/`: optimizer presets
- `training/`: training schedule presets
- `experiment/`: small override bundles (e.g., debug)
- `eval/`: CORE eval defaults
- `presets/`: fully specified runnable presets

## Basic Commands

```bash
# defaults
python train.py

# explicit groups
python train.py model_size=tiny mlp=gec_shared

# with experiment override
python train.py +experiment=debug

# preset
python train.py --config-name=presets/gec_shared_tiny
```

## Notes

- `NANOCHAT_BASE_DIR` must be set.
- `data.data_path` defaults to `${oc.env:NANOCHAT_BASE_DIR}/base_data`.
- `data.tokenizer_dir` defaults to `${oc.env:NANOCHAT_BASE_DIR}/tokenizer`.
