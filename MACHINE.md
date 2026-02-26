# Machine: A5000 Server

## Required Environment Variables

Add to ~/.bashrc:
```bash
export NANOCHAT_BASE_DIR=/data2/.cache/nanochat
```

## Conda Environment

### nanochat (primary)
- **Path**: `/data2/hanchi/miniconda3/envs/nanochat`
- **Python**: `/data2/hanchi/miniconda3/envs/nanochat/bin/python`
- **torchrun**: `/data2/hanchi/miniconda3/envs/nanochat/bin/torchrun`
- **Python version**: 3.12
- **PyTorch**: 2.9.1+cu128
- **CUDA**: 12.8

### gec (legacy)
- **Path**: `/data2/hanchi/miniconda3/envs/gec`
- **Python**: `/data2/hanchi/miniconda3/envs/gec/bin/python3.12`


**Always use the absolute path to the conda environment and python!!!**

## Data Paths (derived from NANOCHAT_BASE_DIR)

| Item | Path |
|------|------|
| FineWeb-edu | `$NANOCHAT_BASE_DIR/base_data/` (1823 shards) |
| Tokenizer | `$NANOCHAT_BASE_DIR/tokenizer/tokenizer.pkl` |
| Eval bundle | `$NANOCHAT_BASE_DIR/eval_bundle/` |

## Storage Notes

On this A5000 machine, always store data in `/data2/` and never in `$HOME/`, as `$HOME/` is small storage that fills up quickly.

## Running Training

```bash
cd /data2/hanchi/Global-Expert-Choice
/data2/hanchi/miniconda3/envs/nanochat/bin/python train.py
```

## Tokenizer Config ($100 tier)
- vocab_size: 65,536
- max_chars: 2B
- Compression: ~4.85 chars/token
