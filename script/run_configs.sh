#!/usr/bin/env bash
set -euo pipefail

# Hardware config is read from environment variables consumed by `train.sh`:
# N_GPUS, MODEL_SIZE, TRAINING_TOKENS, MICRO_BATCH_SIZE.

# ============================================
# Experiments
# ============================================

# Dense baseline
# ./script/train.sh --mlp dense

# EC + shared expert (no Expert Parallelism)
# ./script/train.sh --mlp ec --g 2 --e 8 --cutoff-alpha 0.999 --no-ep

# EC + shared expert (EP)
./script/train.sh --mlp ec --g 2 --e 8 --cutoff-alpha 0.999

# ET + shared expert (threshold routing with implied EC warmup)
./script/train.sh --mlp et --g 2 --e 8 --cutoff-alpha 0.999

# Token-choice
./script/train.sh --mlp token_choice --g 2 --e 8 --shared-expert

# Token-choice with aux loss
./script/train.sh --mlp token_choice --g 2 --e 8 --shared-expert --load-balance aux --aux-coef 0.001

# Token-choice with DeepSeek load balancing
./script/train.sh --mlp token_choice --g 2 --e 8 --shared-expert --load-balance deepseek --deepseek-lr 0.001

# ET with capacity constraints
./script/train.sh --mlp et --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.25

# Explicit warmup override
# ./script/train.sh --mlp et --g 2 --e 8 --cutoff-alpha 0.999 --warmup 1000

# Custom batch size
# ./script/train.sh --mlp dense --batch-size 262144

# Softmax router activation
# sigmoid, softmax_e, softmax_e_shared_out
# ./script/train.sh --mlp ec --g 2 --e 8 --router softmax_e
