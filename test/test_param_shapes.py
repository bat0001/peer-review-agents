"""Diagnostic test to identify parameters with incompatible shapes for distributed training."""

import sys
import torch
import torch.distributed as dist
from omegaconf import OmegaConf

# Add project root to path
sys.path.insert(0, '/data2/hanchi/nano_gec')

from src.models import BaseGPT, ModelConfig
from hydra import initialize, compose


def check_param_shapes_for_dist(world_size=8):
    """Check all model parameters for distributed training compatibility."""

    # Initialize Hydra and load config
    with initialize(version_base=None, config_path="../configs"):
        cfg = compose(config_name="config", overrides=[
            "model_size=tiny",
            "mlp=gec_shared_capacity",
            "model.expert_capacity_factor=0.2"
        ])

    # Create model
    print("Creating model...")
    model_config = ModelConfig(**cfg.model)
    model = BaseGPT(model_config)
    model = model.cuda()

    print(f"\n{'='*80}")
    print(f"Checking parameter shapes for world_size={world_size}")
    print(f"{'='*80}\n")

    issues = []
    all_params = []

    for name, param in model.named_parameters():
        shape = param.shape
        first_dim = shape[0] if len(shape) > 0 else 1
        divisible = first_dim % world_size == 0

        param_info = {
            'name': name,
            'shape': shape,
            'first_dim': first_dim,
            'divisible': divisible,
            'requires_grad': param.requires_grad,
        }
        all_params.append(param_info)

        if not divisible:
            issues.append(param_info)

    # Print all parameters
    print(f"Total parameters: {len(all_params)}\n")

    for p in all_params:
        status = "✓" if p['divisible'] else "✗"
        grad_status = "grad" if p['requires_grad'] else "no_grad"
        print(f"{status} {p['name']:<60} {str(p['shape']):<30} {grad_status}")

    # Print issues
    if issues:
        print(f"\n{'='*80}")
        print(f"FOUND {len(issues)} PARAMETERS WITH INCOMPATIBLE SHAPES:")
        print(f"{'='*80}\n")

        for issue in issues:
            print(f"Parameter: {issue['name']}")
            print(f"  Shape: {issue['shape']}")
            print(f"  First dimension: {issue['first_dim']}")
            print(f"  Divisible by {world_size}: {issue['divisible']}")
            print(f"  Requires grad: {issue['requires_grad']}")
            print()

        return False
    else:
        print(f"\n{'='*80}")
        print("✓ All parameters have compatible shapes for distributed training!")
        print(f"{'='*80}\n")
        return True


def check_buffers_for_dist(world_size=8):
    """Check all model buffers (might be wrongly registered as params)."""

    # Initialize Hydra and load config
    with initialize(version_base=None, config_path="../configs"):
        cfg = compose(config_name="config", overrides=[
            "model_size=tiny",
            "mlp=gec_shared_capacity",
            "model.expert_capacity_factor=0.2"
        ])

    # Create model
    model_config = ModelConfig(**cfg.model)
    model = BaseGPT(model_config)
    model = model.cuda()

    print(f"\n{'='*80}")
    print(f"Checking model buffers")
    print(f"{'='*80}\n")

    for name, buffer in model.named_buffers():
        print(f"Buffer: {name:<60} {str(buffer.shape):<30} requires_grad={buffer.requires_grad}")


def simulate_optimizer_grouping(world_size=8):
    """Simulate how the optimizer groups parameters."""

    # Initialize Hydra and load config
    with initialize(version_base=None, config_path="../configs"):
        cfg = compose(config_name="config", overrides=[
            "model_size=tiny",
            "mlp=gec_shared_capacity",
            "model.expert_capacity_factor=0.2"
        ])

    # Create model
    model_config = ModelConfig(**cfg.model)
    model = BaseGPT(model_config)
    model = model.cuda()

    print(f"\n{'='*80}")
    print(f"Simulating optimizer parameter grouping")
    print(f"{'='*80}\n")

    # Group parameters like the training script does
    from src.optimizers.param_groups import group_params_by_optimizer_and_shape

    param_groups = group_params_by_optimizer_and_shape(model, cfg.optimizer)

    for group_name, group_info in param_groups.items():
        print(f"\n{group_name}:")
        print(f"  Optimizer: {group_info.get('optimizer_type', 'unknown')}")
        print(f"  Num params: {len(group_info.get('params', []))}")

        for i, param in enumerate(group_info.get('params', [])):
            shape = param.shape
            first_dim = shape[0] if len(shape) > 0 else 1
            divisible = first_dim % world_size == 0
            status = "✓" if divisible else "✗"

            # Try to find parameter name
            param_name = "unknown"
            for name, p in model.named_parameters():
                if p is param:
                    param_name = name
                    break

            print(f"    {status} [{i}] {param_name:<50} {str(shape):<30}")


if __name__ == "__main__":
    world_size = int(sys.argv[1]) if len(sys.argv) > 1 else 8

    print("\n" + "="*80)
    print("DISTRIBUTED TRAINING PARAMETER SHAPE DIAGNOSTIC")
    print("="*80)

    # Check all parameters
    params_ok = check_param_shapes_for_dist(world_size)

    # Check buffers
    check_buffers_for_dist(world_size)

    # Simulate optimizer grouping
    simulate_optimizer_grouping(world_size)

    sys.exit(0 if params_ok else 1)
