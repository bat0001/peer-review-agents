#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=8
#SBATCH --nodes=1         
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --mem=128GB      
#SBATCH --time=24:00:00
#SBATCH --job-name=train-d12
#SBATCH --error=logs/sbatch/train-d12-%j.err # Use date-based directory
#SBATCH --output=logs/sbatch/train-d12-%j.log # Use date-based directory
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
# export MODEL_SIZE="d12" TRAINING_TOKENS="10"
export MODEL_SIZE="d12" TRAINING_TOKENS="30"
export MICRO_BATCH_SIZE=32 # I am on B200 baby!



echo "=== d12 30B Job Started ==="

# ./script/run_configs.sh

# Dense baseline
# ./script/train.sh --mlp dense

# Token-choice 
# ./script/train.sh --mlp tc_shared --g 2 --e 8 

# Token-choice with aux loss
# ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance aux --aux-coef 0.001

# Token-choice with DeepSeek load balancing
# ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.001

########### GEC Shared No Norm ###########


# Ablation 1: no normalization
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none

# Warmup 4000 steps
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none --capacity 0.5 --warmup 4000

# GEC Shared topk: 
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none


# GEC Shared no ep:
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none --no-ep

# # GEC Shared Threshold faster ema:
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.997 --capacity 0.5 --norm none




echo "=== d12 30B Job Complete ==="

# # Experiment config
# export MODEL_SIZE="d20" TRAINING_TOKENS="11.2"
# export MICRO_BATCH_SIZE=16 # We halve the batch size because we might OOM on B200

# echo "=== d20 Job Started ==="

# # Dense baseline
# ./script/train.sh --mlp dense 

# # GEC shared (no Expert Parallelism)
# # ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --no-ep

# # GEC shared (EP) top-k bsz 262144
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999

# # GEC with capacity constraints (auto-enables threshold)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5

# # Token-choice 
# # ./script/train.sh --mlp tc_shared --g 2 --e 8 

# # Token-choice with aux loss
# # ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance aux --aux-coef 0.001

# # Token-choice with DeepSeek load balancing
# # ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.001

# echo "=== d20 Job Complete ==="