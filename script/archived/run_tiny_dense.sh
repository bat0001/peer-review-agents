#!/bin/bash
# Train tiny dense baseline
# WandB project: ec-shared-experiments

set -e  # Exit on error

# ============================================
# Hardware settings
# ============================================
GPUS="1,3,4,5"
N_GPUS=4

# Training settings
TOTAL_BATCH_SIZE=524288
PER_DEVICE_BATCH_SIZE=16
SEQ_LENGTH=1024

# Output directory
OUTPUT_BASE="./log/dense"
EXP_NAME="dense"

# ============================================
# Derived settings
# ============================================
GRAD_ACCUM=$((TOTAL_BATCH_SIZE / (N_GPUS * PER_DEVICE_BATCH_SIZE * SEQ_LENGTH)))

echo "Dense Baseline | GPUs: ${GPUS} | Batch: ${TOTAL_BATCH_SIZE} | GradAccum: ${GRAD_ACCUM}"

# Create output directory
mkdir -p "${OUTPUT_BASE}/${EXP_NAME}"

# Set environment variables
export CUDA_VISIBLE_DEVICES="${GPUS}"
export MASTER_ADDR="localhost"
export MASTER_PORT=29503

# Run training
/data2/hanchi/miniconda3/envs/gec/bin/torchrun \
    --nproc_per_node=${N_GPUS} \
    --nnodes=1 \
    --node_rank=0 \
    --master_addr="${MASTER_ADDR}" \
    --master_port="${MASTER_PORT}" \
    train.py \
    mlp=dense \
    model_size=tiny \
    training=standard \
    experiment_name="${EXP_NAME}" \
    training.total_batch_size=${TOTAL_BATCH_SIZE} \
    training.per_device_batch_size=${PER_DEVICE_BATCH_SIZE} \
    training.sequence_length=${SEQ_LENGTH} \
    logging.wandb_project=ec-shared-experiments \
    output_dir="${OUTPUT_BASE}" \
    2>&1 | tee "${OUTPUT_BASE}/${EXP_NAME}/train.log"

echo "Done. Log: ${OUTPUT_BASE}/${EXP_NAME}/train.log"
