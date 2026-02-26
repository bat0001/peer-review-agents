#!/usr/bin/env bash
set -euo pipefail

# Train RustBPE tokenizer from local parquet shards using in-repo code only.
# Usage:
#   ./script/train_tokenizer.sh [vocab_size] [max_chars]
# Example:
#   ./script/train_tokenizer.sh 65536 2000000000

VOCAB_SIZE="${1:-65536}"
MAX_CHARS="${2:-2000000000}"
PYTHON_BIN="${PYTHON_BIN:-/data2/hanchi/miniconda3/envs/nanochat/bin/python}"

"${PYTHON_BIN}" -u -m src.data.train_tokenizer \
  --vocab-size "${VOCAB_SIZE}" \
  --max-chars "${MAX_CHARS}"
