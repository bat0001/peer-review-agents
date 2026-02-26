#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=8
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --mem=128GB
#SBATCH --time=24:00:00
#SBATCH --job-name=train-d12
#SBATCH --error=logs/sbatch/train-d12-%j.err
#SBATCH --output=logs/sbatch/train-d12-%j.log
#SBATCH --mail-type=END,FAIL,TIME_LIMIT,START
#SBATCH --mail-user=ryansunhanchi@gmail.com
#SBATCH --exclusive

set -euo pipefail

# Environment setup
export NANOCHAT_BASE_DIR=/orange/yonghui.wu/hanchi/.cache/nanochat
export HF_HOME=/orange/yonghui.wu/hanchi/.cache/huggingface
export TORCH_HOME=/orange/yonghui.wu/hanchi/.cache/torch
export PIP_CACHE_DIR=/orange/yonghui.wu/hanchi/.cache/pip

# Initialize and activate conda (batch jobs don't source .bashrc)
source /apps/conda/25.1.1/etc/profile.d/conda.sh
conda activate /orange/yonghui.wu/hanchi/conda_envs/nanochat

# Hardware config
export N_GPUS=8

# Experiment config
export MODEL_SIZE="d12" TRAINING_TOKENS="10"
export MICRO_BATCH_SIZE=32

echo "=== d12 Training Started ==="

########### DENSE BASELINE ###########

./script/train.sh --mlp dense


## Notes: always use norm none, as fanout proven to be suboptimal for all EC/GEC models.

########### EC SHARED  ###########
### Note: EC include all runs using top-k, though mode might be called gec_shared

# Chunked routing, chunk_size=1, routing_bsz 2048
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --chunk_size 1 --cutoff-alpha 0.999

# Chunked routing, chunk_size=4, routing_bsz 8192
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --chunk_size 4 --cutoff-alpha 0.999

# Top-k without Expert Parallelism, routing_bsz 65536
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none --no-ep

# Top-k with Expert Parallelism, routing_bsz 524288
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none

########### GEC SHARED (main focus) ###########

# Threshold + Capacity
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none

# Threshold + Capacity + Warmup 4000
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --warmup 4000

# Threshold + Capacity + Faster EMA (alpha 0.99)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.99 --capacity 0.5 --norm none --warmup 4000

# Threshold + Capacity + warmup/switch=200 + ema-start=200 (alpha sweep)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.99 --capacity 0.5 --norm none --warmup 200 --ema-start 200
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --warmup 200 --ema-start 200
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --warmup 2000 --ema-start 200
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --warmup 500 --ema-start 200
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.997 --capacity 0.5 --norm none --warmup 500 --ema-start 200
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.99 --capacity 1 --norm none --warmup 500 --ema-start 200

########### TC SHARED ###########

# Basic
# ./script/train.sh --mlp tc_shared --g 2 --e 8

# Aux Loss
# ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance aux --aux-coef 0.001

# DeepSeek Load Balancing
# ./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.001

########### GEC (no shared) - ablation ###########

# Top-k
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --norm none

# Threshold + Capacity
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none

########### TC (no shared) - ablation ###########

# Basic
# ./script/train.sh --mlp tc --g 2 --e 8

echo "=== d12 Training Complete ==="
