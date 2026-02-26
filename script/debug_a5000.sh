# **Note**: 
# 1. if you are an coding agent updating this script, do not delete any existing lines/runs but instead just comment them out.
# 2. here, you should only add end-to-end debug script/train.sh runs with different mode. It's not for testing.


export N_GPUS=8
# export CUDA_VISIBLE_DEVICES=1,2,3,4,5,6,7,8
export CUDA_VISIBLE_DEVICES=0,2,3,4,5,6,7,9
export MODEL_SIZE="d8" TRAINING_TOKENS="0.01"
export MICRO_BATCH_SIZE=4

# Quick debug - GEC shared with EP 
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug
# Passed!

# test normalization mode none
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --norm none
# Passed!

# test 2
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --capacity 0.25 --norm none

# GEC EP
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --norm none

# GEC EP capacity constraints
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --capacity 0.25 --norm none

# GEC no ep
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --norm none --no-ep

# GEC shared no ep (repro eval dtype mismatch)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none --no-ep

# regular TC
# ./script/train.sh --mlp tc --g 2 --e 8 --experiment debug

# Routing warmup (switch to threshold at step 20)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --warmup 20
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --warmup 20 --no-ep

# Routing warmup + capacity (warmup overrides auto-threshold=0)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --capacity 0.25 --warmup 60 --norm none
# ./script/train.sh --mlp gec --g 2 --e 8 --cutoff-alpha 0.999 --experiment debug --capacity 0.25 --warmup 60 --norm none --no-ep

# EC_shared chunked routing (vary routing_chunk_seqs; requires bsz divisible by chunk size)
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --experiment debug --chunk_size 4 model.routing_chunk_seqs=1
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --experiment debug --chunk_size 4 model.routing_chunk_seqs=2
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --experiment debug --chunk_size 4 model.routing_chunk_seqs=4

# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --experiment debug --chunk_size 1
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --experiment debug --chunk_size 2
# ./script/train.sh --mlp ec_shared --g 2 --e 8 --norm none --no-ep --experiment debug --chunk_size 4

# GEC shared threshold runs (smaller debug schedule, warmup/switch==ema-start)
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.99 --capacity 0.5 --norm none --experiment debug --warmup 20 --ema-start 20
# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --experiment debug --warmup 20 --ema-start 20

# GEC shared threshold runs (end-to-end debug for ema-start vs warmup behavior)
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --experiment debug --warmup 2000 --ema-start 200
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --capacity 0.5 --norm none --experiment debug --warmup 500 --ema-start 200
./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.997 --capacity 0.5 --norm none --experiment debug --warmup 500 --ema-start 200

# ./script/train.sh --mlp gec_shared --g 2 --e 8 --cutoff-alpha 0.999 --norm none --no-ep --experiment debug
