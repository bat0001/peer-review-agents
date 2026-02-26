#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64GB
#SBATCH --time=04:00:00
#SBATCH --job-name=expert-specialization
#SBATCH --output=logs/sbatch/expert-specialization-%j.log
#SBATCH --error=logs/sbatch/expert-specialization-%j.err
#SBATCH --mail-type=END,FAIL,TIME_LIMIT,START
#SBATCH --mail-user=ryansunhanchi@gmail.com


set -euo pipefail

REPO_DIR=/orange/yonghui.wu/hanchi/nanochat-integration
cd "${REPO_DIR}"


# Environment setup
export NANOCHAT_BASE_DIR=/orange/yonghui.wu/hanchi/.cache/nanochat
export HF_HOME=/orange/yonghui.wu/hanchi/.cache/huggingface
export TORCH_HOME=/orange/yonghui.wu/hanchi/.cache/torch
export PIP_CACHE_DIR=/orange/yonghui.wu/hanchi/.cache/pip

source /apps/conda/25.1.1/etc/profile.d/conda.sh
conda activate /orange/yonghui.wu/hanchi/conda_envs/nanochat

PY=/orange/yonghui.wu/hanchi/conda_envs/nanochat/bin/python

# Install datasets if missing
if ! "${PY}" -c "import datasets" 2>/dev/null; then
  "${PY}" -m pip install datasets
fi

# Prefetch HF datasets
${PY} -c "
from datasets import load_dataset
load_dataset('openai/gsm8k', 'main', split='train')
load_dataset('openai/openai_humaneval', split='test')
"

OUT=outputs

# alias -> checkpoint path (all at step 19073)
declare -A CKPTS=(
  ["gec_shared_warmup"]="${OUT}/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup4000_alpha0.999_ep8/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup4000_alpha0.999_ep8/checkpoints/checkpoint_step_19073.pt"
  ["ec_shared_bsz2k"]="${OUT}/ec_shared_d12_G2E8_10B_normnone_chunk1_alpha0.999/ec_shared_d12_G2E8_10B_normnone_chunk1_alpha0.999/checkpoints/checkpoint_step_19073.pt"
  ["ec_shared_bsz8k"]="${OUT}/ec_shared_d12_G2E8_10B_normnone_chunk4_alpha0.999/ec_shared_d12_G2E8_10B_normnone_chunk4_alpha0.999/checkpoints/checkpoint_step_19073.pt"
  ["ec_shared_bsz64k"]="${OUT}/gec_shared_d12_G2E8_10B_normnone_alpha0.999/gec_shared_d12_G2E8_10B_normnone_alpha0.999/checkpoints/checkpoint_step_19073.pt"
  ["ec_shared_bsz512k"]="${OUT}/gec_shared_d12_G2E8_10B_normnone_alpha0.999_ep8/gec_shared_d12_G2E8_10B_normnone_alpha0.999_ep8/checkpoints/checkpoint_step_19073.pt"
  ["gec_shared_warmup500_ema200_a0997"]="${OUT}/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup500_ema200_alpha0.997_ep8/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup500_ema200_alpha0.997_ep8/checkpoints/checkpoint_step_19073.pt"
  ["gec_shared_warmup500_ema200_a0999"]="${OUT}/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup500_ema200_alpha0.999_ep8/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup500_ema200_alpha0.999_ep8/checkpoints/checkpoint_step_19073.pt"
  ["gec_shared_warmup2000_ema200_a0999"]="${OUT}/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup2000_ema200_alpha0.999_ep8/gec_shared_d12_G2E8_10B_cap0.5_normnone_warmup2000_ema200_alpha0.999_ep8/checkpoints/checkpoint_step_19073.pt"
  ["gec_shared_thresh0"]="${OUT}/gec_shared_d12_G2E8_10B_cap0.5_thresh0_ep8/gec_shared_d12_G2E8_10B_cap0.5_thresh0_ep8/checkpoints/checkpoint_step_19073.pt"
)

# needs_fix=0
# for alias in "${!CKPTS[@]}"; do
#   if [[ "${CKPTS[$alias]}" == *"_ep"*"/checkpoints/"*.pt ]]; then
#     needs_fix=1
#     break
#   fi
# done
# if [[ "${needs_fix}" -eq 1 ]]; then
#   ${PY} -m script.fix_ep_checkpoint_indices
# fi

for alias in "${!CKPTS[@]}"; do
  ckpt="${CKPTS[$alias]}"
  echo "=== ${alias} ==="

  if [[ "${ckpt}" == *"_ep"*"/checkpoints/"*.pt ]]; then
    fixed_ckpt="${ckpt%.pt}_fixed.pt"
    if [[ -f "${fixed_ckpt}" ]]; then
      ckpt="${fixed_ckpt}"
    fi
  fi

  if [[ ! -f "${ckpt}" ]]; then
    echo "WARNING: checkpoint not found: ${ckpt}" >&2
    continue
  fi

  ${PY} -m expert_specialization \
    +analysis=expert_specialization \
    analysis.checkpoint_path="${ckpt}" \
    analysis.output_dir="outputs/expert_specialization_${alias}"
done
