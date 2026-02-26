# Machine: B200 Server (HiPerGator)

## Required Environment Variables

Add to ~/.bashrc:
```bash
export NANOCHAT_BASE_DIR=/orange/yonghui.wu/hanchi/.cache/nanochat
```

## Conda Environment

### nanochat (primary)
- **Path**: `/orange/yonghui.wu/hanchi/conda_envs/nanochat`
- **Python**: `/orange/yonghui.wu/hanchi/conda_envs/nanochat/bin/python`
- **torchrun**: `/orange/yonghui.wu/hanchi/conda_envs/nanochat/bin/torchrun`
- **Python version**: 3.12
- **PyTorch**: 2.9.1+cu128
- **CUDA**: 12.8

## Data Paths (derived from NANOCHAT_BASE_DIR)

| Item | Path |
|------|------|
| FineWeb-edu | `$NANOCHAT_BASE_DIR/base_data/` |
| Tokenizer | `$NANOCHAT_BASE_DIR/tokenizer/tokenizer.pkl` |
| Eval bundle | `$NANOCHAT_BASE_DIR/eval_bundle/` |

## Storage Notes

On HiPerGator, always store data in `/orange/yonghui.wu/hanchi/` and never in `$HOME/`, due to quota limits.

## Cache Directories

| Service | Variable | Path |
|---------|----------|------|
| HuggingFace | `HF_HOME` | `/orange/yonghui.wu/hanchi/.cache/huggingface` |
| PyTorch | `TORCH_HOME` | `/orange/yonghui.wu/hanchi/.cache/torch` |
| pip | `PIP_CACHE_DIR` | `/orange/yonghui.wu/hanchi/.cache/pip` |

## Tokenizer Config ($100 tier)
- vocab_size: 65,536
- max_chars: 2B
- Compression: ~4.85 chars/token
