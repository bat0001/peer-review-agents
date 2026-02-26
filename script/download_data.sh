#!/usr/bin/env bash
set -euo pipefail

# Download FineWeb-Edu parquet shards using this repo's dataset module.
# Usage:
#   ./script/download_data.sh [num_files] [num_workers]
# Example:
#   ./script/download_data.sh -1 8

NUM_FILES="${1:--1}"
NUM_WORKERS="${2:-8}"
PYTHON_BIN="${PYTHON_BIN:-/data2/hanchi/miniconda3/envs/nanochat/bin/python}"

"${PYTHON_BIN}" -u -m src.data.nanochat_dataset \
  --num-files "${NUM_FILES}" \
  --num-workers "${NUM_WORKERS}"
