"""Test shared expert weighting for GEC_shared with normalization_mode=none."""

import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.model_base import ModelConfig
from src.models.gec_shared import GECSharedMLP


def _zero_routed_weights(model: GECSharedMLP) -> None:
    with torch.no_grad():
        for w in model.engine.expert_weight1:
            w.zero_()
        for w in model.engine.expert_weight2:
            w.zero_()


def test_gec_shared_none_keeps_shared_unweighted() -> None:
    torch.manual_seed(0)

    config = ModelConfig(
        model_type="gec_shared",
        n_embd=16,
        n_layer=1,
        n_head=1,
        granularity=2,
        expansion=2,
        router_activation="sigmoid",
        normalization_mode="none",
    )

    model = GECSharedMLP(config)
    model.routing_mode = "threshold"
    model.eval()

    with torch.no_grad():
        model.shared_weight1.fill_(0.01)
        model.shared_weight2.fill_(0.01)

    _zero_routed_weights(model)

    x = torch.randn(2, 3, config.n_embd)
    output, _ = model(x)

    shared_flat = model._shared_expert_forward(x.view(-1, config.n_embd))
    shared_out = shared_flat.view_as(output)

    assert shared_out.abs().sum().item() > 0.0
    assert torch.allclose(output, shared_out, atol=1e-5, rtol=1e-5)


def test_gec_shared_none_threshold_bf16_no_dtype_mismatch() -> None:
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        return

    torch.manual_seed(0)

    config = ModelConfig(
        model_type="gec_shared",
        n_embd=16,
        n_layer=1,
        n_head=1,
        granularity=2,
        expansion=2,
        router_activation="sigmoid",
        normalization_mode="none",
    )

    model = GECSharedMLP(config).cuda()
    model.routing_mode = "threshold"
    model.eval()

    x = torch.randn(2, 3, config.n_embd, device="cuda", dtype=torch.bfloat16)
    with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
        output, _ = model(x)

    assert output.dtype == x.dtype


if __name__ == "__main__":
    test_gec_shared_none_keeps_shared_unweighted()
    test_gec_shared_none_threshold_bf16_no_dtype_mismatch()
    print("ok")
