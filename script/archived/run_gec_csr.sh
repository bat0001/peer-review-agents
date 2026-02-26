#!/bin/bash
# Run GEC (Global Expert Choice) with CSR backend
# Model: tiny GEC (no shared expert)
# Backend: CSR (token-parallel)
# GPUs: 2-9 (8 GPUs)

set -e  # Exit on error

# Configuration
GPUS="2,3,4,5,6,7,8,9"
N_GPUS=8

# Training settings
TRAINING_CONFIG="quick"  # Uses configs/training/quick.yaml (524k batch, 0.5 epoch)
WANDB_PROJECT="gec-shared-experiments"  # Use ec-experiments wandb project

# Experiment name
EXP_NAME="gec_shared_csr_tiny"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}GEC CSR Backend Training${NC}"
echo -e "${BLUE}=====================================${NC}"
echo "Model: tiny GEC_shared (Global Expert Choice, shared expert)"
echo "Backend: CSR (token-parallel)"
echo "GPUs: ${GPUS} (${N_GPUS} devices)"
echo "Training config: ${TRAINING_CONFIG}"
echo "Wandb project: ${WANDB_PROJECT}"
echo "Experiment: ${EXP_NAME}"
echo ""

# Check GPU availability
echo "=== GPU Status ==="
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv
echo ""

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Starting experiment: ${EXP_NAME}${NC}"
echo -e "${GREEN}=====================================${NC}"

# Set environment variables
export CUDA_VISIBLE_DEVICES="${GPUS}"

# IMPORTANT: Before running, switch backend to CSR in src/models/engines/__init__.py
# Uncomment: ExpertEngine = ExpertEngineCSR
echo -e "${BLUE}Note: Make sure CSR backend is enabled in src/models/engines/__init__.py${NC}"
echo -e "${BLUE}The script will continue in 5 seconds...${NC}"
sleep 5

# Run training with torchrun using Hydra config
/data2/hanchi/miniconda3/envs/gec/bin/torchrun \
    --nproc_per_node=${N_GPUS} \
    train.py \
    model_size=tiny \
    mlp=gec_shared \
    training=${TRAINING_CONFIG} \
    training.compile_model=true \
    experiment_name="${EXP_NAME}" \
    logging.wandb_project="${WANDB_PROJECT}"

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Experiment completed: ${EXP_NAME}${NC}"
echo -e "${GREEN}Results in: ./outputs/${EXP_NAME}${NC}"
echo -e "${GREEN}=====================================${NC}"
