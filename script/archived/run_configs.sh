#!/usr/bin/env bash
set -euo pipefail

# Hardware config comes from SLURM (N_GPUS, MODEL_SIZE, TRAINING_TOKENS, MICRO_BATCH_SIZE)

# ============================================
# Experiments
# ============================================

# Dense baseline
# ./script/train.sh --mlp dense 

# GEC shared (no Expert Parallelism)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --no-ep

# GEC shared (EP)
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999

# Token-choice 
./script/train.sh --mlp tc_shared --g 2 --e 8 

# Token-choice with aux loss
./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance aux --aux-coef 0.001

# Token-choice with DeepSeek load balancing
./script/train.sh --mlp tc_shared --g 2 --e 8 --load-balance deepseek --deepseek-lr 0.001

# GEC with capacity constraints (auto-enables threshold)
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.25



# GEC with explicit threshold warmup
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --warmup 1000

# Custom batch size
# ./script/train.sh --mlp dense --batch-size 262144

# Softmax router activation
# sigmoid, softmax_e, softmax_e, softmax_e_shared_out
# none, fanout
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --router softmax_e --norm none
