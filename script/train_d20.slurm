#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=8
#SBATCH --nodes=1         
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --mem=128GB      
#SBATCH --time=24:00:00
#SBATCH --job-name=train-d20
#SBATCH --error=logs/sbatch/train-d20-%j.err # Use date-based directory
#SBATCH --output=logs/sbatch/train-d20-%j.log # Use date-based directory
#SBATCH --mail-type=END,FAIL,TIME_LIMIT,START
#SBATCH --mail-user=ryansunhanchi@gmail.com
#SBATCH --exclusive

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

# Hardware config
export N_GPUS=8

# Experiment config
# # Experiment config
export MODEL_SIZE="d20" TRAINING_TOKENS="11.2"
export MICRO_BATCH_SIZE=16 # We halve the batch size because we might OOM on B200

echo "=== d20 Job Started ==="

# # Dense baseline
./script/train.sh --mlp dense 

# NOTE: Always use norm none for d20!
# GEC shared (no Expert Parallelism)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --no-ep

# GEC shared (EP) top-k bsz 262144
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none

# # GEC with capacity constraints (auto-enables threshold)
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --warmup 4000

# Token-choice 
# ./script/train.sh --mlp tc_shared --g 2 --e 8 

# Token-choice with aux loss
./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance aux --aux-coef 0.001

# Token-choice with DeepSeek load balancing
# ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.001

echo "=== d20 Job Complete ==="