"""
Distributed training utilities for multi-GPU runs without a DDP-wrapped model.

Provenance:
- Adapted from nanochat distributed training patterns:
  https://github.com/karpathy/nanochat
- Modified for GEC expert-parallel initialization and cutoff-state synchronization.
"""

import os
import torch
import torch.distributed as dist


def is_ddp() -> bool:
    """Check if running in distributed mode."""
    return int(os.environ.get('RANK', -1)) != -1


def get_dist_info() -> tuple[bool, int, int, int]:
    """
    Get distributed training info.

    Returns:
        (is_distributed, rank, local_rank, world_size)
    """
    if is_ddp():
        assert all(var in os.environ for var in ['RANK', 'LOCAL_RANK', 'WORLD_SIZE']), \
            "Distributed mode requires RANK, LOCAL_RANK, and WORLD_SIZE environment variables"
        return (
            True,
            int(os.environ['RANK']),
            int(os.environ['LOCAL_RANK']),
            int(os.environ['WORLD_SIZE'])
        )
    else:
        return False, 0, 0, 1


def print0(s="", **kwargs):
    """Print only on rank 0."""
    if int(os.environ.get('RANK', 0)) == 0:
        print(s, **kwargs)


def is_dist_initialized() -> bool:
    """Return True when torch.distributed is available and initialized."""
    return dist.is_available() and dist.is_initialized()


def barrier_if_initialized() -> None:
    """Synchronize ranks when distributed is initialized."""
    if is_dist_initialized():
        dist.barrier()


def compute_init(seed: int = 42, expert_parallel: bool = False):
    """
    Initialize compute environment (CUDA, distributed, precision).

    Args:
        seed: Random seed for reproducibility
        expert_parallel: If True, use rank-specific seeds for divergent expert init

    Returns:
        (is_distributed, rank, local_rank, world_size, device)
    """
    assert torch.cuda.is_available(), "CUDA required"

    # Distributed setup (need rank for EP seed)
    ddp, rank, local_rank, world_size = get_dist_info()

    # Reproducibility: EP mode uses rank-specific seed for divergent expert init
    if expert_parallel and ddp:
        effective_seed = seed + rank
    else:
        effective_seed = seed

    torch.manual_seed(effective_seed)
    torch.cuda.manual_seed(effective_seed)

    # Precision: TF32 for matmuls
    torch.set_float32_matmul_precision("high")

    if ddp:
        device = torch.device("cuda", local_rank)
        torch.cuda.set_device(device)
        dist.init_process_group(backend="nccl", device_id=device)
        dist.barrier()
        if expert_parallel:
            print0(f"Initialized distributed EP: {world_size} GPUs (rank-specific seeds)")
        else:
            print0(f"Initialized distributed: {world_size} GPUs")
    else:
        device = torch.device("cuda")
        print0("Single GPU training")

    return ddp, rank, local_rank, world_size, device


def init_model_weights(model, expert_parallel: bool = False):
    """Initialize model weights, handling EP/DP correctly.

    Call AFTER model.to_empty(device).

    For EP mode:
    1. Each rank already has rank-specific seed (from compute_init)
    2. init_weights() creates divergent params
    3. broadcast_dp_params() syncs DP params from rank 0

    Args:
        model: The model to initialize
        expert_parallel: If True, broadcast DP params from rank 0
    """
    model.init_weights()

    if expert_parallel and is_ddp():
        broadcast_dp_params(model)
        print0("✓ DP params broadcast from rank 0")


def broadcast_dp_params(model):
    """Broadcast DP params from rank 0. Skip EP expert weights.

    This ensures DP params are identical across ranks while EP expert
    weights remain divergent (each rank owns different experts).
    """
    for name, param in model.named_parameters():
        if 'expert_weight' in name:
            continue  # EP: keep divergent
        dist.broadcast(param.data, src=0)

    for name, buffer in model.named_buffers():
        if buffer is not None:
            dist.broadcast(buffer, src=0)


def reduce_mean_scalar(value: float, device: torch.device) -> float:
    """Reduce a scalar across ranks by mean."""
    if not dist.is_initialized():
        return value
    tensor = torch.tensor([value], device=device, dtype=torch.float32)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor /= dist.get_world_size()
    return float(tensor.item())


def reduce_mean_list(values: list[float], device: torch.device) -> list[float]:
    """Reduce a list of scalars across ranks by mean."""
    if not dist.is_initialized():
        return values
    tensor = torch.tensor(values, device=device, dtype=torch.float32)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor /= dist.get_world_size()
    return tensor.cpu().tolist()


def compute_cleanup():
    """Cleanup distributed process group."""
    if is_ddp():
        dist.destroy_process_group()
