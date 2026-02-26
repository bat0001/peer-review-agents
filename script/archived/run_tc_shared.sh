#!/bin/bash
# Train Token-Choice MoE with optional shared expert
# Supports: scattermoe_tc (no shared) and tc_shared (with shared expert)
# Load balancing: none, aux, aux_error, or deepseek
# WandB project: ec-shared-experiments

set -e  # Exit on error

# ============================================
# CONFIGURABLE OPTIONS
# ============================================
# Set these before running:
SHARED=true           # true = tc_shared, false = scattermoe_tc
LOAD_BALANCE="aux"  # "none", "aux", "aux_error", or "deepseek"

# ============================================
# Hardware settings
# ============================================
# GPUS="6,7,8,9"  # 8 GPUs (avoiding GPU 0,1 which may be in use)
GPUS="1,3,4,5"
N_GPUS=4

# Training settings
TOTAL_BATCH_SIZE=524288
PER_DEVICE_BATCH_SIZE=16
SEQ_LENGTH=1024

# DeepSeek bias settings (only used if LOAD_BALANCE=deepseek)
DEEPSEEK_BIAS_LR=0.005

# Aux loss settings (only used if LOAD_BALANCE=aux)
AUX_LOSS_COEF=0.01

# First layer dense (no routing for L0)
FIRST_LAYER_DENSE=true

# Output directory
OUTPUT_BASE="./log/tc_shared"

# ============================================
# Derived settings
# ============================================
if [ "${SHARED}" = "true" ]; then
    MLP_TYPE="tc_shared"
else
    MLP_TYPE="scattermoe_tc"
fi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}Token-Choice MoE Training${NC}"
echo -e "${BLUE}=====================================${NC}"
echo "MLP type: ${MLP_TYPE}"
echo "Load balance: ${LOAD_BALANCE}"
echo "GPUs: ${GPUS} (${N_GPUS} devices)"
echo "Total batch size: ${TOTAL_BATCH_SIZE} tokens"
echo "Per-device batch size: ${PER_DEVICE_BATCH_SIZE} samples"
echo "Sequence length: ${SEQ_LENGTH} tokens"
echo "Gradient accumulation steps: $((TOTAL_BATCH_SIZE / (N_GPUS * PER_DEVICE_BATCH_SIZE * SEQ_LENGTH)))"
echo "WandB project: ec-shared-experiments"
echo ""

# Create output directory
mkdir -p "${OUTPUT_BASE}"

# Build load balance args and experiment name
LOAD_BALANCE_ARGS=""
if [ "${LOAD_BALANCE}" = "deepseek" ]; then
    LOAD_BALANCE_ARGS="model.load_balance_method=deepseek model.deepseek_bias_lr=${DEEPSEEK_BIAS_LR}"
    EXP_NAME="${MLP_TYPE}_deepseek_${DEEPSEEK_BIAS_LR}"
    echo "DeepSeek bias LR: ${DEEPSEEK_BIAS_LR}"
elif [ "${LOAD_BALANCE}" = "aux" ]; then
    LOAD_BALANCE_ARGS="model.load_balance_method=aux model.aux_loss_coef=${AUX_LOSS_COEF}"
    EXP_NAME="${MLP_TYPE}_aux_${AUX_LOSS_COEF}"
    echo "Aux loss coefficient: ${AUX_LOSS_COEF}"
elif [ "${LOAD_BALANCE}" = "aux_error" ]; then
    LOAD_BALANCE_ARGS="model.load_balance_method=aux_error model.aux_loss_coef=${AUX_LOSS_COEF}"
    EXP_NAME="${MLP_TYPE}_aux_error_${AUX_LOSS_COEF}"
    echo "Aux error coefficient: ${AUX_LOSS_COEF}"
else
    LOAD_BALANCE_ARGS="model.load_balance_method=none"
    EXP_NAME="${MLP_TYPE}_none"
fi
echo ""

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Starting experiment: ${EXP_NAME}${NC}"
echo -e "${GREEN}=====================================${NC}"

# Create experiment output directory
mkdir -p "${OUTPUT_BASE}/${EXP_NAME}"

# Set environment variables
export CUDA_VISIBLE_DEVICES="${GPUS}"
export MASTER_ADDR="localhost"
export MASTER_PORT=29503  # Different port to avoid conflicts

# Run training with torchrun and Hydra config
/data2/hanchi/miniconda3/envs/gec/bin/torchrun \
    --nproc_per_node=${N_GPUS} \
    --nnodes=1 \
    --node_rank=0 \
    --master_addr="${MASTER_ADDR}" \
    --master_port="${MASTER_PORT}" \
    train.py \
    mlp=${MLP_TYPE} \
    model_size=tiny \
    training=standard \
    experiment_name="${EXP_NAME}" \
    model.first_layer_dense=${FIRST_LAYER_DENSE} \
    ${LOAD_BALANCE_ARGS} \
    training.total_batch_size=${TOTAL_BATCH_SIZE} \
    training.per_device_batch_size=${PER_DEVICE_BATCH_SIZE} \
    training.sequence_length=${SEQ_LENGTH} \
    logging.wandb_project=ec-shared-experiments \
    output_dir="${OUTPUT_BASE}" \
    2>&1 | tee "${OUTPUT_BASE}/${EXP_NAME}/train.log"

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Training completed!${NC}"
echo -e "${GREEN}Results saved to: ${OUTPUT_BASE}/${EXP_NAME}${NC}"
echo -e "${GREEN}=====================================${NC}"
