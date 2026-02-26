"""Test that refactored models still work correctly."""

import torch
import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.gec import GECMLP
from src.models.gec_shared import GECSharedMLP


@dataclass
class TestConfig:
    n_embd: int = 64
    n_layer: int = 2
    n_experts: int = 4
    expansion: int = 4
    granularity: int = 4
    router_activation: str = 'sigmoid'
    cutoff_ema_alpha: float = 0.99
    expert_capacity_factor: float = -1.0  # Disabled by default


def test_models():
    """Test GEC and GEC_shared with both topk and threshold routing."""
    torch.manual_seed(42)

    config = TestConfig()
    B, T = 2, 8

    print("=" * 60)
    print("Testing Refactored Models")
    print("=" * 60)

    for model_name, ModelClass in [("GEC", GECMLP), ("GEC_shared", GECSharedMLP)]:
        print(f"\n{model_name}:")
        print("-" * 40)

        model = ModelClass(config)

        # Test both topk and threshold modes
        for mode in ['topk', 'threshold']:
            print(f"  Mode: {mode}")

            model.routing_mode = mode
            if mode == 'topk':
                model.train()
            else:
                model.eval()

            x = torch.randn(B, T, config.n_embd)

            # Forward pass
            output, metrics = model(x)

            # Check output
            if torch.isfinite(output).all():
                print(f"    ✓ Output finite (mean={output.mean().item():.4f})")
            else:
                print(f"    ✗ Output contains NaN/Inf!")
                return False

            # Check metrics
            if len(metrics) > 0:
                print(f"    ✓ {len(metrics)} metrics computed")
            else:
                print(f"    ✗ No metrics!")
                return False

    # Test capacity mode for GEC_shared
    print(f"\nGEC_shared with capacity:")
    print("-" * 40)

    config_cap = TestConfig()
    config_cap.expert_capacity_factor = 0.2

    model = GECSharedMLP(config_cap)
    model.routing_mode = 'threshold'
    model.train()

    x = torch.randn(B, T, config_cap.n_embd)
    output, metrics = model(x)

    if torch.isfinite(output).all():
        print(f"  ✓ Output finite (mean={output.mean().item():.4f})")
    else:
        print(f"  ✗ Output contains NaN/Inf!")
        return False

    has_capacity = any('capacity' in k.lower() for k in metrics.keys())
    if has_capacity:
        print(f"  ✓ Capacity metrics present")
    else:
        print(f"  ⚠ No capacity metrics")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_models()
    sys.exit(0 if success else 1)
