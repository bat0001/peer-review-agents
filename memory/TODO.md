- [ ] absorb the 

```python
# train.py line 75
model_config.threshold_warmup_steps = config.training.threshold_warmup_steps
```

into the model config class.

- [ ] Learning rate schedule has duplicates in train.py and utils.py
- [ ] Is utils.py necessary?

- optimizer config, is this necessary?

```python
 # Get optimizer config with defaults
    opt_config = getattr(config, 'optimizer', {})
    if isinstance(opt_config, dict):
        unembedding_lr = opt_config.get('unembedding_lr', 0.004)
        embedding_lr = opt_config.get('embedding_lr', 0.2)
        matrix_lr = opt_config.get('matrix_lr', 0.02)
        warmup_ratio = opt_config.get('warmup_ratio', 0.0)
        warmdown_ratio = opt_config.get('warmdown_ratio', 0.2)
        final_lr_frac = opt_config.get('final_lr_frac', 0.0)
        weight_decay = opt_config.get('weight_decay', 0.0)
    else:
        # Use defaults if no optimizer config
        unembedding_lr = 0.004
        embedding_lr = 0.2
        matrix_lr = 0.02
        warmup_ratio = 0.0
        warmdown_ratio = 0.2
        final_lr_frac = 0.0
        weight_decay = 0.0
```

- [ ] Question: why we have orig_model and model in the train.py file?

- [ ] what's this: 

```python
# Check for threshold mode switch
        if step == config.training.threshold_warmup_steps and config.training.threshold_warmup_steps >= 0:
            # Print cutoff_ema values before switching (debug)
            if rank == 0:
                for i, block in enumerate(orig_model.blocks):
                    if hasattr(block.mlp, 'cutoff_ema'):
                        cutoff_mean = block.mlp.cutoff_ema.mean().item()
                        cutoff_max = block.mlp.cutoff_ema.max().item()
                        print0(f"  Layer {i}: cutoff_ema mean={cutoff_mean:.4f}, max={cutoff_max:.4f}")
                        break  # Just show first layer
```

- [ ] why is eval metrics called charts on wandb?

- [ ] Root directory: clean up the tests
- [x] Root directory: move @IMPLEMENTATION.md to memory, do we archive it? → Done: moved to `memory/archive/deprecated/IMPLEMENTATION.md`

- [ ] Whay does model_base.py has config?