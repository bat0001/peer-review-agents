#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64GB
#SBATCH --time=48:00:00
#SBATCH --job-name=setup-nanochat
#SBATCH --error=logs/sbatch/setup-%j.err
#SBATCH --output=logs/sbatch/setup-%j.log
#SBATCH --mail-type=END,FAIL,TIME_LIMIT,START
#SBATCH --mail-user=ryansunhanchi@gmail.com

set -euo pipefail

# Environment setup
export NANOCHAT_BASE_DIR=/orange/yonghui.wu/hanchi/.cache/nanochat
export HF_HOME=/orange/yonghui.wu/hanchi/.cache/huggingface
export TORCH_HOME=/orange/yonghui.wu/hanchi/.cache/torch
export PIP_CACHE_DIR=/orange/yonghui.wu/hanchi/.cache/pip
export PYTHONPATH="/orange/yonghui.wu/hanchi/nanochat-integration/nanochat_260111${PYTHONPATH:+:$PYTHONPATH}"

# Initialize and activate conda (batch jobs don't source .bashrc)
source /apps/conda/25.1.1/etc/profile.d/conda.sh
conda activate /orange/yonghui.wu/hanchi/conda_envs/nanochat

# Create log directory
# mkdir -p logs/sbatch

# Step 1: Install dependencies
echo "=== Installing dependencies ==="
./script/install.sh

# Step 2: Download pretrain data
# echo "=== Downloading pretrain data ==="
# ./script/download_data.sh

# Step 3: Train tokenizer
# echo "=== Training tokenizer ==="
# ./script/train_tokenizer.sh

# echo "=== Setup complete ==="
