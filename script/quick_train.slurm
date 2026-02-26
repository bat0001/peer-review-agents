#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=2
#SBATCH --nodes=1         
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=28
#SBATCH --mem=128GB      
#SBATCH --time=24:00:00
#SBATCH --job-name=quick-train
#SBATCH --error=logs/sbatch/quick-train-%j.err # Use date-based directory
#SBATCH --output=logs/sbatch/quick-train-%j.log # Use date-based directory
#SBATCH --mail-type=END,FAIL,TIME_LIMIT,START
#SBATCH --mail-user=ryansunhanchi@gmail.com

set -euo pipefail

# Environment setup
export NANOCHAT_BASE_DIR=/orange/yonghui.wu/hanchi/.cache/nanochat
export HF_HOME=/orange/yonghui.wu/hanchi/.cache/huggingface
export TORCH_HOME=/orange/yonghui.wu/hanchi/.cache/torch
export PIP_CACHE_DIR=/orange/yonghui.wu/hanchi/.cache/pip
# export PYTHONPATH="/orange/yonghui.wu/hanchi/nanochat-integration/nanochat_260111${PYTHONPATH:+:$PYTHONPATH}"

# Initialize and activate conda (batch jobs don't source .bashrc)
source /apps/conda/25.1.1/etc/profile.d/conda.sh
conda activate /orange/yonghui.wu/hanchi/conda_envs/nanochat

# Create log directory
# mkdir -p logs/sbatch

export N_GPUS=2
export MODEL_SIZE="d12" TRAINING_TOKENS="10"
export MICRO_BATCH_SIZE=32 # I am on B200 baby!

echo "=== Job Started ==="

# GEC shared with EP
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999

# TC shared, Deepseek load balancing
./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.005

echo "=== Job Complete ==="