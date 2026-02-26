"""Debug test to track down NaN source."""

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
    expert_capacity_factor: float = 0.2


# Monkey-patch to add debug output
original_forward_threshold = ExpertEngine.forward_threshold

def debug_forward_threshold(self, x, layer_idx=0, is_shared=False):
    print(f"\n=== forward_threshold debug ===")
    print(f"Input: shape={x.shape}, finite={torch.isfinite(x).all()}")

    # Call original, but wrap _batched_expert_forward
    original_batched = self._batched_expert_forward

    def debug_batched(x_batched):
        print(f"  _batched_expert_forward input: shape={x_batched.shape}, finite={torch.isfinite(x_batched).all()}")
        result = original_batched(x_batched)
        print(f"  _batched_expert_forward output: shape={result.shape}, finite={torch.isfinite(result).all()}")
        if not torch.isfinite(result).all():
            print(f"    NaN count: {torch.isnan(result).sum()}, Inf count: {torch.isinf(result).sum()}")
        return result

    self._batched_expert_forward = debug_batched

    try:
        output, metrics = original_forward_threshold(self, x, layer_idx, is_shared)
        print(f"Output: shape={output.shape}, finite={torch.isfinite(output).all()}")
        if not torch.isfinite(output).all():
            print(f"  NaN count: {torch.isnan(output).sum()}, Inf count: {torch.isinf(output).sum()}")
        return output, metrics
    finally:
        self._batched_expert_forward = original_batched


ExpertEngine.forward_threshold = debug_forward_threshold


if __name__ == "__main__":
    torch.manual_seed(42)

    config = MinimalConfig()
    engine = ExpertEngine(config, n_routed_experts=4)
    engine.train()
    engine.cutoff_ema_raw.fill_(-1.0)

    x = torch.randn(2, 8, config.n_embd)

    output, metrics = engine.forward_threshold(x, layer_idx=0, is_shared=False)

    print(f"\n=== Final result ===")
    print(f"Output finite: {torch.isfinite(output).all()}")
