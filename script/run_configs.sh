#!/usr/bin/env bash
set -euo pipefail

# Hardware config is read from environment variables consumed by `train.sh`:
# N_GPUS, MODEL_SIZE, TRAINING_TOKENS, MICRO_BATCH_SIZE.

# ============================================
# Experiments
# ============================================

# Dense baseline
# ./script/train.sh --mlp dense 

# Expert choice + shared expert (no Expert Parallelism)
# ./script/train.sh --mlp expert_choice --g 2 --e 8 --cutoff-alpha 0.999 --no-ep

# Expert choice + shared expert (EP)
./script/train.sh --mlp expert_choice --g 2 --e 8 --cutoff-alpha 0.999

# Token-choice
./script/train.sh --mlp token_choice --g 2 --e 8 --shared-expert

# Token-choice with aux loss
./script/train.sh --mlp token_choice --g 2 --e 8 --shared-expert --load-balance aux --aux-coef 0.001

# Token-choice with DeepSeek load balancing
./script/train.sh --mlp token_choice --g 2 --e 8 --shared-expert --load-balance deepseek --deepseek-lr 0.001

# Expert choice with capacity constraints (auto-enables threshold)
./script/train.sh --mlp expert_choice --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.25



# Expert choice with explicit threshold warmup
# ./script/train.sh --mlp expert_choice --g 2 --e 8 --cutoff-alpha 0.999 --warmup 1000

# Custom batch size
# ./script/train.sh --mlp dense --batch-size 262144

# Softmax router activation
# sigmoid, softmax_e, softmax_e_shared_out
# ./script/train.sh --mlp expert_choice --g 2 --e 8 --router softmax_e
