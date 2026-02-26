# Hydra Configuration Migration

**Date:** 2025-10-14
**Status:** Completed
**Related:** `configs/README.md`, `src/config.py`, `train.py`

## Summary

Migrated the project from argparse-based configuration to Hydra for composable, flexible config management.

## What Changed

### 1. Config Structure
Created modular Hydra config groups:

```
configs/
├── config.yaml              # Base configuration
├── model_size/              # Model scale (micro/tiny/small/medium/large)
├── mlp/                     # MLP type (dense/gec/gec_shared/ec)
├── experiment/              # Experiment settings (debug/ablation_*/full_run)
├── training/                # Training regime (quick/standard/long)
├── presets/                 # Ready-to-run combinations
└── legacy_configs/          # Old monolithic configs (deprecated)
```

### 2. Code Changes

**src/config.py:**
- Added `hydra-core` and `omegaconf` imports
- Added `ConfigStore` registration
- Added metadata fields (`model_size_name`, `mlp_type_name`)
- Kept backward compatibility with `get_config()` (deprecated)

**train.py:**
- Replaced ~80 lines of argparse + manual overrides
- Now uses `@hydra.main()` decorator (~60 lines total)
- Much cleaner and more maintainable

**requirements.txt:**
- Added `hydra-core>=1.3.2`
- Added `omegaconf>=2.3.0`

### 3. Config Composition

Configs compose in this order (later overrides earlier):
1. `config.yaml` (base)
2. `model_size/*.yaml`
3. `mlp/*.yaml`
4. `training/*.yaml`
5. `experiment/*.yaml` (overrides last)
6. Command-line overrides

Note: `_self_` placement controls when base config values apply.

## Usage Examples

### Old System (Deprecated)
```bash
python train.py --config configs/gec_shared_tiny.yaml \
  --router-activation relu \
  --learning-rate 0.001 \
  --no-compile
```

### New System (Hydra)
```bash
# Simple composition
python train.py model_size=tiny mlp=gec_shared

# Specific overrides
python train.py model.router_activation=relu training.learning_rate=0.001

# Debug mode (no compile, no wandb)
python train.py +experiment=debug

# Ablation sweeps (runs 4 experiments)
python train.py --multirun \
  +experiment=ablation_router \
  model.router_activation=sigmoid,relu,softmax_k,softmax_e
```

## Benefits

1. **Composability**: Mix model_size + mlp type + experiment + training regime
2. **Less boilerplate**: No more large argparse definitions
3. **Type safety**: Kept dataclasses + added runtime validation
4. **Sweeps**: `--multirun` for easy hyperparameter searches
5. **Cleaner CLI**: `model.n_layer=16` instead of `--n-layer 16`

## Design Decisions

### Config Group Naming

- **model_size/** (not `model/`): Separates "how big" from "what type"
- **mlp/** (not `model_type/`): Semantic clarity (MLP architecture)
- **experiment/**: Experimental setup (ablations, debug, full runs)
- **training/**: Training regime (duration, batch sizes)
- **presets/**: Common combinations for convenience

### Metadata Fields

Added `model_size_name` and `mlp_type_name` as top-level fields for experiment naming:
```yaml
experiment_name: "${mlp_type_name}-${model_size_name}-${now:%Y%m%d-%H%M%S}"
```

These are injected by config groups using `@package _global_`.

### Debug Experiment

`experiment/debug.yaml` includes:
- `compile_model: false` (fast startup)
- `use_wandb: false` (no logging overhead)
- `total_batch_size: 65536` (small batch)
- `per_device_batch_size: 4` (minimal GPU memory)
- `max_steps: 100` (quick iterations)

### Backward Compatibility

- Old `get_config()` function kept but deprecated
- Legacy configs moved to `configs/legacy_configs/`
- Can still load old configs if needed for reference

## Testing

✅ Config loading
✅ Validation
✅ Overrides
✅ Presets
✅ Help output (`--help`, `--cfg job`)
✅ Config composition order

## Future Considerations

- Could add more presets for common ablation studies
- Could create config groups for optimizer settings
- Could add config sweeper plugins for advanced hyperparameter tuning
- May want to update trainer to accept `DictConfig` directly instead of converting to dataclass

## Bug Fixes (Post-Migration)

**2025-10-18: Preset config fixes**

Fixed two issues with preset configs when used with `--config-name=presets/<name>`:

1. **Hydra metadata filtering** (src/config.py:183-212):
   - Hydra adds internal metadata fields (`presets`, `hydra`, `defaults`) during config composition
   - `Config.from_dict()` now filters these out before passing to dataclass constructor
   - Prevents `TypeError: Config.__init__() got an unexpected keyword argument 'presets'`

2. **Preset completeness** (configs/presets/*.yaml):
   - Preset configs must be self-contained with all required base fields
   - Added `@package _global_` directive to ensure fields are at top level
   - Included: `output_dir`, `data`, `model.vocab_size`, `training`, `logging`
   - Prevents missing field errors when presets are used as primary config

This enables ablation scripts to reliably use presets via `--config-name=presets/gec_shared_tiny`.

## References

- Hydra docs: https://hydra.cc/
- Config groups: https://hydra.cc/docs/tutorials/structured_config/config_groups/
- Defaults list: https://hydra.cc/docs/advanced/defaults_list/
