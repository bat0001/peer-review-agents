#!/usr/bin/env bash
set -euo pipefail

# Defaults (can be overridden by env vars for SLURM compatibility)
N_GPUS=${N_GPUS:-1}
MODEL_SIZE=${MODEL_SIZE:-}
TRAINING_TOKENS=${TRAINING_TOKENS:-}
MICRO_BATCH_SIZE=${MICRO_BATCH_SIZE:-}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mlp)          MLP="$2"; shift 2;;
        --g)            G="$2"; shift 2;;
        --e)            E="$2"; shift 2;;
        --capacity)     CAPACITY_FACTOR="$2"; shift 2;;
        --warmup)       WARMUP_STEPS="$2"; shift 2;;
        --ema-start)    EMA_START_STEPS="$2"; shift 2;;
        --load-balance) LOAD_BALANCE_METHOD="$2"; shift 2;;
        --deepseek-lr)  DEEPSEEK_BIAS_LR="$2"; shift 2;;
        --aux-coef)     AUX_LOSS_COEF="$2"; shift 2;;
        --router)       ROUTER_ACTIVATION="$2"; shift 2;;
        --norm)         NORMALIZATION_MODE="$2"; shift 2;;
        --cutoff-alpha) CUTOFF_EMA_ALPHA="$2"; shift 2;;
        --batch-size)   TOTAL_BATCH_SIZE="$2"; shift 2;;
        --bsz)          MICRO_BATCH_SIZE="$2"; shift 2;;
        --micro-batch-size) MICRO_BATCH_SIZE="$2"; shift 2;;
        --chunk_size)   ROUTING_CHUNK_SEQS="$2"; shift 2;;
        --name)         EXPERIMENT_NAME="$2"; shift 2;;
        --experiment)   EXPERIMENT="$2"; shift 2;;
        --no-ep)        NO_EP=1; shift;;
        *)              echo "Unknown arg: $1"; exit 1;;
    esac
done

# Required
: "${MODEL_SIZE:?MODEL_SIZE must be set (via env var or SLURM)}"
: "${MLP:?MLP must be set (via --mlp argument)}"
: "${TRAINING_TOKENS:?TRAINING_TOKENS must be set (via env var or SLURM)}"
[[ "${MLP}" != "dense" ]] && : "${G:?G must be set for MoE models (via --g)}" "${E:?E must be set for MoE models (via --e)}"

# EP is only supported for gec/gec_shared
if [[ "${MLP}" != "gec_shared" && "${MLP}" != "gec" ]]; then
    [[ -z "${NO_EP:-}" ]] && NO_EP=1
    echo "EP disabled for mlp=${MLP} (only gec/gec_shared support EP)."
fi

# Fixed values
SEQ_LEN=2048
BLOCK_SIZE=2048

# Auto-enable threshold routing if capacity factor is set
if [[ -n "${CAPACITY_FACTOR:-}" && -z "${WARMUP_STEPS:-}" ]]; then
    WARMUP_STEPS="0"  # Enable threshold from step 0
fi

# Build experiment name if not set
if [[ -z "${EXPERIMENT_NAME:-}" ]]; then
    EXPERIMENT_NAME="${MLP}_${MODEL_SIZE}"
    [[ "${MLP}" != "dense" ]] && EXPERIMENT_NAME+="_G${G}E${E}"
    EXPERIMENT_NAME+="_${TRAINING_TOKENS}B"

    # Add optional config suffixes
    [[ -n "${CAPACITY_FACTOR:-}" ]]     && EXPERIMENT_NAME+="_cap${CAPACITY_FACTOR}"
    [[ -n "${LOAD_BALANCE_METHOD:-}" ]] && EXPERIMENT_NAME+="_${LOAD_BALANCE_METHOD}"
    [[ -n "${DEEPSEEK_BIAS_LR:-}" ]]    && EXPERIMENT_NAME+="_dslr${DEEPSEEK_BIAS_LR}"
    [[ -n "${AUX_LOSS_COEF:-}" ]]       && EXPERIMENT_NAME+="_aux${AUX_LOSS_COEF}"
    [[ -n "${ROUTER_ACTIVATION:-}" ]]   && EXPERIMENT_NAME+="_${ROUTER_ACTIVATION}"
    [[ -n "${NORMALIZATION_MODE:-}" ]]   && EXPERIMENT_NAME+="_norm${NORMALIZATION_MODE}"
    [[ -n "${ROUTING_CHUNK_SEQS:-}" ]]    && EXPERIMENT_NAME+="_chunk${ROUTING_CHUNK_SEQS}"
    [[ -n "${WARMUP_STEPS:-}" && "${WARMUP_STEPS}" != "-1" ]] && EXPERIMENT_NAME+="_warmup${WARMUP_STEPS}"
    [[ -n "${EMA_START_STEPS:-}" ]]      && EXPERIMENT_NAME+="_ema${EMA_START_STEPS}"
    [[ -n "${CUTOFF_EMA_ALPHA:-}" ]]    && EXPERIMENT_NAME+="_alpha${CUTOFF_EMA_ALPHA}"
    [[ -z "${NO_EP:-}" ]] && EXPERIMENT_NAME+="_ep${N_GPUS}"
fi

# Build args
args=(
    "model_size=${MODEL_SIZE}"
    "mlp=${MLP}"
    "training.training_tokens=${TRAINING_TOKENS}"
    "training.sequence_length=${SEQ_LEN}"
    "+model.block_size=${BLOCK_SIZE}"
    "experiment_name=${EXPERIMENT_NAME}"
)

[[ "${MLP}" != "dense" ]] && args+=("model.granularity=${G}" "model.expansion=${E}")

# Optional args (use ++ to override if exists, add if doesn't)
[[ -n "${TOTAL_BATCH_SIZE:-}" ]]    && args+=("training.total_batch_size=${TOTAL_BATCH_SIZE}")
[[ -n "${MICRO_BATCH_SIZE:-}" ]]    && args+=("training.per_device_batch_size=${MICRO_BATCH_SIZE}")
[[ -n "${ROUTING_CHUNK_SEQS:-}" ]]  && args+=("++model.routing_chunk_seqs=${ROUTING_CHUNK_SEQS}")
[[ -n "${LOAD_BALANCE_METHOD:-}" ]] && args+=("++model.load_balance_method=${LOAD_BALANCE_METHOD}")
[[ -n "${AUX_LOSS_COEF:-}" ]]       && args+=("++model.aux_loss_coef=${AUX_LOSS_COEF}")
[[ -n "${DEEPSEEK_BIAS_LR:-}" ]]    && args+=("++model.deepseek_bias_lr=${DEEPSEEK_BIAS_LR}")
[[ -n "${CAPACITY_FACTOR:-}" ]]     && args+=("++model.expert_capacity_factor=${CAPACITY_FACTOR}")
[[ -n "${WARMUP_STEPS:-}" ]]        && args+=("++training.threshold_warmup_steps=${WARMUP_STEPS}")
[[ -n "${EMA_START_STEPS:-}" ]]     && args+=("++training.ema_start_steps=${EMA_START_STEPS}")
[[ -n "${ROUTER_ACTIVATION:-}" ]]   && args+=("++model.router_activation=${ROUTER_ACTIVATION}")
[[ -n "${NORMALIZATION_MODE:-}" ]]  && args+=("++model.normalization_mode=${NORMALIZATION_MODE}")
[[ -n "${CUTOFF_EMA_ALPHA:-}" ]]    && args+=("++model.cutoff_ema_alpha=${CUTOFF_EMA_ALPHA}")
[[ -n "${EXPERIMENT:-}" ]]          && args+=("+experiment=${EXPERIMENT}")
[[ -z "${NO_EP:-}" ]]               && args+=("model.expert_parallel=true")
args+=("logging.wandb_project=nanochat-${MODEL_SIZE}")

# Run
export CUDA_VISIBLE_DEVICES
if [[ "${N_GPUS}" -gt 1 ]]; then
    exec torchrun --nproc_per_node="${N_GPUS}" train.py "${args[@]}"
else
    exec python train.py "${args[@]}"
fi
