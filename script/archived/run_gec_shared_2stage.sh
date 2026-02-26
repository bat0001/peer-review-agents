#!/bin/bash
# Two-stage training experiment for GEC_shared with trainable threshold
# Uses built-in threshold warmup mechanism:
#   - Steps 0-999: topk routing (differentiable, perfect load balance)
#   - Steps 1000+: threshold routing (causal, uses EMA cutoffs from topk warmup)
# Uses Hydra config system
# GPUs: 2-9 (8 GPUs)

set -e  # Exit on error

# Configuration
GPUS="2,3,4,5,6,7,8,9"
N_GPUS=8

# Training settings
TRAINING_CONFIG="quick"  # Uses configs/training/quick.yaml (524k batch, 0.5 epoch)
WANDB_PROJECT="ec-shared-experiments"  # New wandb project for 2-stage experiments

# Threshold warmup settings
# THRESHOLD_WARMUP_STEPS=1000  # Switch from topk to threshold at step 1000
# THRESHOLD_WARMUP_STEPS=20 # debug
THRESHOLD_WARMUP_STEPS=0 # no threshold warmup, rely solely on capacity constraints
# THRESHOLD_WARMUP_STEPS=-1 # disabled

# Model settings (matching ec_shared experiments)
MODEL_SIZE="tiny"
MLP_TYPE="gec_shared_capacity"

# Capacity constraints (for threshold routing)
EXPERT_CAPACITY_FACTOR=0.02  # ±2% capacity bounds: [k×0.98, k×1.02], set to -1 to disable

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}GEC_shared Two-Stage Training${NC}"
echo -e "${BLUE}=====================================${NC}"
echo "Model: ${MODEL_SIZE} ${MLP_TYPE}"
echo "GPUs: ${GPUS} (${N_GPUS} devices)"
echo "Training config: ${TRAINING_CONFIG}"
echo "Wandb project: ${WANDB_PROJECT}"
echo "Threshold warmup: ${THRESHOLD_WARMUP_STEPS} steps"
echo "  → Steps 0-$((THRESHOLD_WARMUP_STEPS-1)): topk routing (warmup)"
echo "  → Steps ${THRESHOLD_WARMUP_STEPS}+: threshold routing (inference-like)"
if [ "${EXPERT_CAPACITY_FACTOR}" != "-1" ]; then
    echo "Expert capacity factor: ${EXPERT_CAPACITY_FACTOR} (capacity constraints enabled)"
    echo "  → Bounds: [k×(1-${EXPERT_CAPACITY_FACTOR}), k×(1+${EXPERT_CAPACITY_FACTOR})]"
else
    echo "Expert capacity factor: ${EXPERT_CAPACITY_FACTOR} (pure threshold, no capacity constraints)"
fi
echo ""

# Experiment name
if [ "${EXPERT_CAPACITY_FACTOR}" = "-1" ]; then
    EXP_NAME="gec_shared_threshold_warmup${THRESHOLD_WARMUP_STEPS}"
else
    EXP_NAME="gec_shared_threshold_warmup${THRESHOLD_WARMUP_STEPS}_cap${EXPERT_CAPACITY_FACTOR}"
fi

# Set environment variables
export CUDA_VISIBLE_DEVICES="${GPUS}"

# ============================================
# Run training with threshold warmup
# ============================================
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Starting training with threshold warmup${NC}"
echo -e "${GREEN}=====================================${NC}"

/data2/hanchi/miniconda3/envs/gec/bin/torchrun \
    --nproc_per_node=${N_GPUS} \
    train.py \
    model_size=${MODEL_SIZE} \
    mlp=${MLP_TYPE} \
    training=${TRAINING_CONFIG} \
    training.compile_model=true \
    training.threshold_warmup_steps=${THRESHOLD_WARMUP_STEPS} \
    model.expert_capacity_factor=${EXPERT_CAPACITY_FACTOR} \
    experiment_name="${EXP_NAME}" \
    logging.wandb_project="${WANDB_PROJECT}" \
    training.eval_interval=500

echo -e "${GREEN}Training completed!${NC}"
echo ""

# ============================================
# Summary
# ============================================
echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}Two-stage training completed!${NC}"
echo -e "${BLUE}=====================================${NC}"
echo "Results: outputs/${EXP_NAME}"
echo "Wandb project: ${WANDB_PROJECT}"
echo ""
echo "Training automatically switched from topk to threshold at step ${THRESHOLD_WARMUP_STEPS}"
echo "Check wandb for routing metrics and cutoff EMA values during the switch"
echo -e "${BLUE}=====================================${NC}"
