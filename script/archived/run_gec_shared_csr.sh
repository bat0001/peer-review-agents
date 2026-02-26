#!/bin/bash
# Train GEC_shared with CSR kernel (top-k routing)
# Uses: gec_shared model type with csr scatter backend
# WandB project: ec-shared-experiments

set -e  # Exit on error

# Configuration
OUTPUT_BASE="./log/gec_shared_csr"
GPUS="2,3,4,5,6,7,8,9"  # 8 GPUs (avoiding GPU 0,1 which may be in use)
N_GPUS=8

# Training settings (matching run_ec_experiments.sh)
TOTAL_BATCH_SIZE=524288
PER_DEVICE_BATCH_SIZE=16
SEQ_LENGTH=1024

# SCATTER_BACKEND="csr_optimized"
# SCATTER_BACKEND="csr"
# SCATTER_BACKEND="index_add"
SCATTER_BACKEND="index_add_fp32"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}GEC_shared with CSR Kernel Training${NC}"
echo -e "${BLUE}=====================================${NC}"
echo "GPUs: ${GPUS} (${N_GPUS} devices)"
echo "Total batch size: ${TOTAL_BATCH_SIZE} tokens"
echo "Per-device batch size: ${PER_DEVICE_BATCH_SIZE} samples"
echo "Sequence length: ${SEQ_LENGTH} tokens"
echo "Gradient accumulation steps: $((TOTAL_BATCH_SIZE / (N_GPUS * PER_DEVICE_BATCH_SIZE * SEQ_LENGTH)))"
echo "Scatter backend: ${SCATTER_BACKEND}"
echo "WandB project: ec-shared-experiments"
echo ""

# Create output directory
mkdir -p "${OUTPUT_BASE}"

EXP_NAME="gec_shared_${SCATTER_BACKEND}_fp32accum"

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Starting experiment: ${EXP_NAME}${NC}"
echo -e "${GREEN}=====================================${NC}"

# Create experiment output directory
mkdir -p "${OUTPUT_BASE}/${EXP_NAME}"

# Set environment variables
export CUDA_VISIBLE_DEVICES="${GPUS}"
export MASTER_ADDR="localhost"
export MASTER_PORT=29501  # Different port to avoid conflicts

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
    model.scatter_backend=${SCATTER_BACKEND} \
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
