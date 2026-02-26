"""
Test Expert Parallel engine standalone.

Run with:
    CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 test/test_ep_engine.py
"""

import torch
import torch.distributed as dist
from dataclasses import dataclass


def setup():
    if not dist.is_initialized():
        dist.init_process_group(backend="nccl")
    rank = dist.get_rank()
    torch.cuda.set_device(rank)
    return rank, dist.get_world_size()


@dataclass
class MockConfig:
    """Minimal config for testing."""
    n_embd: int = 32
    expert_dim: int = 64
    router_activation: str = "sigmoid"
    expert_init: str = "default"
    expansion: int = 4
    granularity: int = 1
    n_layer: int = 1
    cutoff_ema_alpha: float = 0.99
    expert_capacity_factor: float = -1.0


def test_topk_forward():
    """Test forward_topk mode."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")

    from src.models.engines.parallel_experts_manual import ParallelExperts

    B, T = 2, 8
    n_routed_experts = 4  # 2 per GPU

    config = MockConfig(n_embd=32, expert_dim=64)
    engine = ParallelExperts(config, n_routed_experts).to(device)

    x = torch.randn(B, T, config.n_embd, device=device, requires_grad=True)

    expert_out, indices, weights, fanout, _shared_weights, metrics = engine.forward_topk(x, layer_idx=0)

    assert expert_out is not None
    assert indices is not None
    assert weights is not None

    # Backward
    loss = expert_out.sum()
    loss.backward()

    assert x.grad is not None
    assert x.grad.shape == x.shape

    if rank == 0:
        print("[PASS] test_topk_forward")
    dist.barrier()


def test_threshold_forward():
    """Test forward_threshold mode."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")

    from src.models.engines.parallel_experts_manual import ParallelExperts

    B, T = 2, 8
    n_routed_experts = 4

    config = MockConfig(n_embd=32, expert_dim=64)
    engine = ParallelExperts(config, n_routed_experts).to(device)
    # Set raw cutoff buffer to 0 so all tokens pass
    engine.cutoff_ema_raw.zero_()

    x = torch.randn(B, T, config.n_embd, device=device, requires_grad=True)

    expert_out, indices, weights, fanout, _shared_weights, metrics = engine.forward_threshold(x, layer_idx=0)

    assert expert_out is not None

    loss = expert_out.sum()
    loss.backward()

    assert x.grad is not None

    if rank == 0:
        print("[PASS] test_threshold_forward")
    dist.barrier()


def test_threshold_sparse():
    """Test threshold mode with sparse activation."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")

    from src.models.engines.parallel_experts_manual import ParallelExperts

    B, T = 2, 8
    n_routed_experts = 4

    config = MockConfig(n_embd=32, expert_dim=64)
    engine = ParallelExperts(config, n_routed_experts).to(device)
    # High raw cutoffs = fewer tokens pass
    engine.cutoff_ema_raw.fill_(2.0)

    x = torch.randn(B, T, config.n_embd, device=device, requires_grad=True)

    expert_out, indices, weights, fanout, _shared_weights, metrics = engine.forward_threshold(x, layer_idx=0)

    loss = expert_out.sum()
    loss.backward()

    assert x.grad is not None

    if rank == 0:
        print("[PASS] test_threshold_sparse")
    dist.barrier()


def main():
    setup()
    rank = dist.get_rank()
    if rank == 0:
        print("=" * 40)
        print("Testing EP Engine")
        print("=" * 40)

    test_topk_forward()
    test_threshold_forward()
    test_threshold_sparse()

    if rank == 0:
        print("=" * 40)
        print("All tests passed!")
        print("=" * 40)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
