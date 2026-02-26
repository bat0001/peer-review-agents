#!/bin/bash
# Train GEC_shared with Expert Parallelism (EP) + Softmax_e routing + Capacity Constraints
# Uses: gec_shared model type with softmax_e or softmax_e_shared_out + capacity factor
# WandB project: ec-shared-experiments

set -e  # Exit on error

# Configuration
OUTPUT_BASE="./log/gec_shared_ep"
GPUS="2,3,4,5,6,7,8,9"  # 8 GPUs (avoiding GPU 0,1 which may be in use)
N_GPUS=8

# Training settings
TOTAL_BATCH_SIZE=524288
PER_DEVICE_BATCH_SIZE=16
SEQ_LENGTH=1024

# Scatter backend for EP
SCATTER_BACKEND="index_add_fp32"

# Router activation: softmax_e or softmax_e_shared_out
# softmax_e: shared IN softmax (anchor logit=0), total weight <= 1
# softmax_e_shared_out: shared OUT of softmax (weight=1/G), total weight <= 1 + 1/G
ROUTER_ACTIVATION="softmax_e"  # Change to "softmax_e_shared_out" for variant

# Capacity constraint
CAPACITY_FACTOR=0.125

# EMA alpha (1 - 1/N for N-step effective window)
CUTOFF_EMA_ALPHA=0.993  # ~333 step window

# First layer dense (no routing for L0)
FIRST_LAYER_DENSE=true

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}GEC_shared with EP + ${ROUTER_ACTIVATION} + Capacity${NC}"
echo -e "${BLUE}=====================================${NC}"
echo "GPUs: ${GPUS} (${N_GPUS} devices)"
echo "Total batch size: ${TOTAL_BATCH_SIZE} tokens"
echo "Per-device batch size: ${PER_DEVICE_BATCH_SIZE} samples"
echo "Sequence length: ${SEQ_LENGTH} tokens"
echo "Gradient accumulation steps: $((TOTAL_BATCH_SIZE / (N_GPUS * PER_DEVICE_BATCH_SIZE * SEQ_LENGTH)))"
echo "Scatter backend: ${SCATTER_BACKEND}"
echo "Expert Parallel: true (world_size=${N_GPUS})"
echo "Router activation: ${ROUTER_ACTIVATION}"
echo "Capacity factor: ${CAPACITY_FACTOR}"
echo "Cutoff EMA alpha: ${CUTOFF_EMA_ALPHA}"
echo "First layer dense: ${FIRST_LAYER_DENSE}"
echo "WandB project: ec-shared-experiments"
echo ""

# Create output directory
mkdir -p "${OUTPUT_BASE}"

# Build experiment name
FLD_SUFFIX=""
if [ "${FIRST_LAYER_DENSE}" = "true" ]; then
    FLD_SUFFIX="_fld"
fi

# Short name for activation
if [ "${ROUTER_ACTIVATION}" = "softmax_e" ]; then
    ACT_SUFFIX="smax"
else
    ACT_SUFFIX="smax_out"
fi

EXP_NAME="gec_shared_${ACT_SUFFIX}_epx${N_GPUS}_C${CAPACITY_FACTOR}${FLD_SUFFIX}"

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Starting experiment: ${EXP_NAME}${NC}"
echo -e "${GREEN}=====================================${NC}"

# Create experiment output directory
mkdir -p "${OUTPUT_BASE}/${EXP_NAME}"

# Set environment variables
export CUDA_VISIBLE_DEVICES="${GPUS}"
export MASTER_ADDR="localhost"
export MASTER_PORT=29504  # Different port to avoid conflicts

# Run training with torchrun and Hydra config
/data2/hanchi/miniconda3/envs/gec/bin/torchrun \
    --nproc_per_node=${N_GPUS} \
    --nnodes=1 \
    --node_rank=0 \
    --master_addr="${MASTER_ADDR}" \
    --master_port="${MASTER_PORT}" \
    train.py \
    mlp=gec_shared \
    model_size=tiny \
    training=standard \
    experiment_name="${EXP_NAME}" \
    model.expert_parallel=true \
    model.scatter_backend=${SCATTER_BACKEND} \
    model.first_layer_dense=${FIRST_LAYER_DENSE} \
    model.router_activation=${ROUTER_ACTIVATION} \
    model.normalization_mode=none \
    +model.cutoff_ema_alpha=${CUTOFF_EMA_ALPHA} \
    +model.expert_capacity_factor=${CAPACITY_FACTOR} \
    training.threshold_warmup_steps=0 \
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
