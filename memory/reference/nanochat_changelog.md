# Nanochat Changelog

## nanochat_260111 (Jan 11, 2026) - Latest

Comparing `nanochat_updated/` (Jan 2026) with `nanochat_260111/` (current upstream).

### Flash Attention 3 Integration
- **New backend**: Loads FA3 from HuggingFace Hub via `get_kernel('varunneal/flash-attention-3')`
- **Native layout**: Uses (B, T, H, D) format - no transpose needed
- **Training**: `flash_attn.flash_attn_func(q, k, v, causal=True, window_size=window_size)`
- **Inference**: `flash_attn.flash_attn_with_kvcache()` with native cache management
- **Performance**: +9% tok/sec for d12 even at ctx=2048

### Sliding Window Attention (SSSL Pattern)
- **New config**: `window_pattern: str = "L"` in GPTConfig
- **Default**: "SSSL" (3 short + 1 long alternating, following GPT-3)
- **Characters**: L=full context, S=half context
- **Final layer**: Always full context regardless of pattern

### Learnable Lambdas for Residual Connections
- **resid_lambdas**: Per-layer residual scaling (init 1.0 = neutral)
- **x0_lambdas**: Skip connection to initial embeddings (init 0.0 = disabled)
- **Forward**: `x = resid_lambdas[i] * x + x0_lambdas[i] * x0` before each block
- **Optimizer**: Separate group with `scalar_lr` parameter (default 0.5)

### Muon Optimizer Overhaul
- **Polar Express**: Replaces Newton-Schulz for orthogonalization ([arXiv:2505.16932](https://arxiv.org/pdf/2505.16932))
  - Per-iteration coefficients for optimal convergence
  - 2% safety factor in normalization
- **NorMuon variance reduction**: Similar to Adafactor's low-rank estimator ([arXiv:2510.05491](https://arxiv.org/pdf/2510.05491))
  - New `beta2=0.95` parameter for variance EMA
- **Cautious weight decay**: Only decays where update and weight agree in sign
- **Weight decay scaling**: `wd_scaled = wd * (12/depth)^2`
- **Weight decay schedule**: Linear decay to zero over training

### Training Script Changes (base_train.py)
- **Gradient clipping**: Removed entirely (was buggy and costs ~2% MFU)
- **LR scaling**: sqrt scaling with batch size (reference: 2^19)
- **New args**: `--aspect_ratio`, `--head_dim`, `--window_pattern`, `--scalar_lr`, `--adam_beta1/beta2`
- **Removed args**: `--grad_clip`
- **Default changes**: `weight_decay` 0.0→0.2, `target_param_data_ratio` 20→8
- **Scaling params**: Uses `num_scaling_params` for Chinchilla calculation (per Kaplan et al.)

### AdamW Optimizer
- **`@torch.compile`**: Added for performance
- **Bug fix**: Epsilon applied before bias correction (standard formulation)
- **Simplified**: Removed small parameter handling (< 1024 elements)

### KVCache Redesign
- **Separate caches**: `k_cache` and `v_cache` instead of combined tensor
- **Eager allocation**: Pre-allocates at construction with explicit device/dtype
- **FA3 format**: (n_layers, B, T, H, D)
- **New API**: `get_layer_cache()`, `advance()`, `cache_seqlens` tensor

### Backward Compatibility
- **Config patching**: `_patch_missing_config_keys()` adds `window_pattern="L"` for old checkpoints
- **Weight patching**: `_patch_missing_keys()` adds `resid_lambdas=1.0`, `x0_lambdas=0.0`

### New Scripts
- **scaling_laws.sh**: FLOPs-controlled scaling experiments (1e18, 3e18, 6e18 budgets × 7 depths)
- **miniseries.sh**: Quick model size sweeps (depths 10-20, ratio=8, vocab=32K)

---

## nanochat_updated (Jan 2026)

Comparing `/data2/hanchi/gec/nanochat` (Oct 2025) with `nanochat_updated/`.

### Build System
- **rustbpe**: Now a pip package (`rustbpe>=0.1.0`), no local Rust/Maturin build
- **Dependencies**: torch 2.8→2.9+, added transformers, matplotlib, ipykernel
- **GPU/CPU groups**: Optional dependency groups with `uv sync --extra gpu/cpu`

### Model Architecture (gpt.py)
- **GQA refactor**: Renamed MQA→GQA, uses PyTorch's `enable_gqa` parameter
- Removed custom `repeat_kv()` function (~14 lines)
- Cleaner rotary embeddings (no manual dtype casting)

### Training
- **Hyperparameters**: warmdown_ratio 0.2→0.4, embedding lr 0.2→0.3
- **Synthetic data**: Identity conversations for personality tuning
- **Resume support**: Data loader returns state_dict for approximate resume

### New Features
- `tasks/customjson.py`: Load custom JSONL conversation data
- `tasks/spellingbee.py`: New eval benchmark
- `dev/runcpu.sh`: CPU/MPS demo with auto device detection
- `dev/gen_synthetic_data.py`: Synthetic data generator example

### Safety & Infrastructure
- Calculator tool hardened (disabled builtins, pattern detection)
- `download_file_with_lock()`: Thread-safe concurrent downloads
- Tokenizer BOS fallback: tries `<|bos|>` then `<|endoftext|>`

### Removed
- `rustbpe/` directory (now pip package)
- `nanochat/configurator.py` (absorbed elsewhere)

### For Fork Maintainers
Key changes to consider:
1. Update rustbpe to pip dependency
2. Adopt GQA via `enable_gqa` if customizing attention
3. Consider approximate resume support in data loader
4. Apply calculator security improvements if exposing LLM tools
