"""Minimal test for ExpertEngine capacity optimization."""

import torch
import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.engines.index_add import ExpertEngine


@dataclass
class MinimalConfig:
    n_embd: int = 64
    n_layer: int = 1
    expansion: int = 4
    granularity: int = 4
    router_activation: str = 'sigmoid'
    cutoff_ema_alpha: float = 0.99
    expert_capacity_factor: float = 0.2  # Enable capacity


def test_engine_capacity():
    """Test ExpertEngine with capacity constraints."""
    torch.manual_seed(42)

    config = MinimalConfig()
    n_routed_experts = 4
    B, T = 2, 8

    print("=" * 60)
    print("Testing ExpertEngine Capacity Optimization")
    print("=" * 60)

    # Create engine
    engine = ExpertEngine(config, n_routed_experts=n_routed_experts)
    engine.train()

    # Initialize weights (required since we're creating engine directly)
    for w in engine.expert_weight1:
        torch.nn.init.xavier_uniform_(w)
    for w in engine.expert_weight2:
        torch.nn.init.xavier_uniform_(w)
    torch.nn.init.xavier_uniform_(engine.router.weight)

    # Initialize raw cutoff EMA buffer to reasonable values
    engine.cutoff_ema_raw.fill_(-1.0)

    # Create input
    x = torch.randn(B, T, config.n_embd)

    print(f"\nInput shape: {x.shape}")
    print(f"n_routed_experts: {n_routed_experts}")
    print(f"expert_capacity_factor: {config.expert_capacity_factor}")

    # Forward pass (threshold mode with capacity)
    print("\nRunning forward_threshold...")
    output, metrics = engine.forward_threshold(x, layer_idx=0, is_shared=False)

    print(f"\nOutput shape: {output.shape}")
    print(f"Output finite: {torch.isfinite(output).all()}")
    print(f"Output mean: {output.mean().item():.4f}")
    print(f"Output std: {output.std().item():.4f}")

    # Check for NaN/Inf
    if not torch.isfinite(output).all():
        print("\n✗ Output contains NaN/Inf!")
        print(f"NaN count: {torch.isnan(output).sum().item()}")
        print(f"Inf count: {torch.isinf(output).sum().item()}")
        return False

    print("\n✓ Output is finite")

    # Check metrics
    print("\nMetrics:")
    for k, v in sorted(metrics.items())[:10]:
        if isinstance(v, torch.Tensor):
            if v.numel() == 1:
                print(f"  {k}: {v.item():.4f}")
            else:
                print(f"  {k}: shape {v.shape}")

    # Check capacity metrics
    has_capacity = any('capacity' in k.lower() for k in metrics.keys())
    if has_capacity:
        print("\n✓ Capacity metrics present")
    else:
        print("\n⚠ No capacity metrics (no experts hit bounds)")

    print("\n" + "=" * 60)
    print("Test passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_engine_capacity()
    sys.exit(0 if success else 1)
