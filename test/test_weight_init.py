#!/usr/bin/env python3
"""
Test weight initialization by measuring actual std of each parameter.

Usage:
    # Single GPU
    CUDA_VISIBLE_DEVICES=0 python test/test_weight_init.py +experiment=debug

    # Multi-GPU (with torchrun)
    CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 test/test_weight_init.py +experiment=debug
"""

import os
import sys
import math
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

import hydra
from omegaconf import DictConfig, OmegaConf
import torch

from src.config import Config
from src.models import BaseGPT, ModelConfig
from src.utils.distributed import compute_init, compute_cleanup, print0


def calculate_expected_std(param_shape, param_name):
    """
    Calculate expected std based on initialization rules.

    Returns:
        expected_std (float): Expected standard deviation
        init_type (str): Type of initialization used
    """
    # Output projections (zero-initialized)
    # Includes: lm_head, c_proj, expert_weight2, shared_weight2
    if 'lm_head.weight' in param_name or 'c_proj.weight' in param_name or 'weight2' in param_name:
        return 0.0, "zero_init"

    # Router (small init for symmetry breaking)
    if 'router.weight' in param_name:
        fan_in = param_shape[1]
        return 1.0 / math.sqrt(fan_in), "router_small_init"

    # Embeddings
    if 'wte.weight' in param_name or 'wpe.weight' in param_name:
        return 1.0, "embedding"

    # All weight matrices use fan-in/fan-out scaling
    if 'weight' in param_name:
        if len(param_shape) == 2:
            # Standard 2D weight matrix (fan_out, fan_in)
            fan_out, fan_in = param_shape[0], param_shape[1]
            init_type = "linear"
        elif len(param_shape) == 3:
            # Expert weights: (n_experts, fan_out, fan_in)
            fan_out, fan_in = param_shape[1], param_shape[2]
            if 'shared_weight' in param_name:
                init_type = "expert_shared"
            else:
                init_type = "expert"
        else:
            return None, "unknown"

        # Aspect-ratio scaled Kaiming initialization (same for all weights)
        std = 1.0 / math.sqrt(fan_in) * min(1.0, math.sqrt(fan_out / fan_in))
        return std, init_type

    # Biases (shouldn't exist, but handle just in case)
    if 'bias' in param_name:
        return 0.0, "bias"

    # Unknown parameter type
    return None, "unknown"


@hydra.main(version_base=None, config_path="../configs", config_name="config")
def main(cfg: DictConfig) -> None:
    """Test weight initialization."""

    # Convert DictConfig to Config dataclass
    config_dict = OmegaConf.to_container(cfg, resolve=True)
    config = Config.from_dict(config_dict)
    config.validate()

    # Initialize compute environment
    ddp, rank, local_rank, world_size, device = compute_init(seed=config.training.seed)

    if rank == 0:
        print("=" * 80)
        print("WEIGHT INITIALIZATION TEST")
        print("=" * 80)

    try:
        test_initialization(config, rank, device)
    finally:
        compute_cleanup()


def test_initialization(config, rank, device):
    """Test weight initialization by measuring actual std."""

    # Model config
    model_config = ModelConfig(**config.model)
    model_config.threshold_warmup_steps = config.training.threshold_warmup_steps

    # Initialize model exactly like train.py
    print0("Creating model on meta device...")
    with torch.device("meta"):
        model = BaseGPT(model_config)

    print0("Moving to device and initializing weights...")
    model.to_empty(device=device)
    model.init_weights()

    print0("Weight initialization complete. Analyzing parameters...\n")

    # Verify all params are finite
    with torch.no_grad():
        for name, param in model.named_parameters():
            if not torch.isfinite(param).all():
                print0(f"❌ ERROR: {name} contains NaN/Inf!")
                return

    print0("✓ All parameters are finite\n")

    # Analyze each parameter
    print0("=" * 100)
    print0(f"{'Parameter Name':<60} {'Shape':<20} {'Init Type':<15} {'Expected Std':<12} {'Actual Std':<12} {'Status'}")
    print0("=" * 100)

    mismatches = []
    total_params = 0

    with torch.no_grad():
        for name, param in model.named_parameters():
            total_params += 1

            # Skip if not a weight matrix (e.g., RoPE embeddings are buffers)
            if param.numel() == 0:
                continue

            # Calculate expected std
            expected_std, init_type = calculate_expected_std(param.shape, name)

            if expected_std is None:
                # Skip unknown parameter types
                continue

            # Calculate actual std
            actual_std = param.std().item()

            # Check if match (with tolerance for random variance)
            # For zero-init, check if exactly zero
            if expected_std == 0.0:
                matches = (actual_std == 0.0)
                tolerance = 0.0
            else:
                # Allow 20% relative tolerance for random variance
                tolerance = expected_std * 0.2
                matches = abs(actual_std - expected_std) < tolerance

            status = "✓" if matches else "⚠️  MISMATCH"

            # Format output
            shape_str = str(tuple(param.shape))
            expected_str = f"{expected_std:.6f}"
            actual_str = f"{actual_std:.6f}"

            print0(f"{name:<60} {shape_str:<20} {init_type:<15} {expected_str:<12} {actual_str:<12} {status}")

            if not matches:
                mismatches.append({
                    'name': name,
                    'shape': param.shape,
                    'init_type': init_type,
                    'expected': expected_std,
                    'actual': actual_std,
                    'diff': abs(actual_std - expected_std),
                })

    print0("=" * 100)
    print0(f"\nTotal parameters analyzed: {total_params}")
    print0(f"Mismatches: {len(mismatches)}")

    # Print detailed mismatch report
    if mismatches:
        print0("\n" + "=" * 80)
        print0("DETAILED MISMATCH REPORT")
        print0("=" * 80)
        for m in mismatches:
            print0(f"\n⚠️  {m['name']}")
            print0(f"   Shape: {m['shape']}")
            print0(f"   Init Type: {m['init_type']}")
            print0(f"   Expected Std: {m['expected']:.6f}")
            print0(f"   Actual Std: {m['actual']:.6f}")
            print0(f"   Difference: {m['diff']:.6f} ({m['diff']/m['expected']*100:.1f}% relative error)")
    else:
        print0("\n✅ All weight initializations match expected values!")

    # Special check: Verify expert outputs are zero-initialized
    print0("\n" + "=" * 80)
    print0("EXPERT OUTPUT ANALYSIS (should be zero-initialized)")
    print0("=" * 80)

    with torch.no_grad():
        for name, param in model.named_parameters():
            # Check expert down-projection weights
            if 'weight2' in name:
                actual_std = param.std().item()
                # Zero-init is expected (nanochat style for output projections)
                if actual_std == 0.0:
                    print0(f"✓ {name}: std={actual_std:.6f} (zero-initialized)")
                else:
                    print0(f"⚠️  {name}: std={actual_std:.6f} - SHOULD BE ZERO!")

    print0("=" * 80)


if __name__ == "__main__":
    main()
