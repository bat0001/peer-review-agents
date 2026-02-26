"""Smoke test for ScatterMoE token-choice MLP (CUDA-only)."""

import torch

from src.models.model_base import ModelConfig
from src.models.scattermoe_tc import ScatterMoETokenChoiceMLP


def test_scattermoe_tc_forward_backward():
    if not torch.cuda.is_available():
        return

    config = ModelConfig(
        model_type="scattermoe_tc",
        n_embd=32,
        n_layer=1,
        n_head=4,
        granularity=2,
        expansion=2,
        router_activation="sigmoid",
        load_balance_method="none",
    )

    model = ScatterMoETokenChoiceMLP(config).cuda()
    x = torch.randn(2, 4, config.n_embd, device="cuda", requires_grad=True)

    y, metrics = model(x)
    assert y.shape == x.shape
    assert "expert_usage" in metrics

    loss = y.sum()
    loss.backward()

    assert model.router.weight.grad is not None
    assert model.expert_weight1.grad is not None
    assert model.expert_weight2.grad is not None
