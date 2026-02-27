"""Checkpoint save/load utilities with EP-aware mapping."""

import torch
import torch.distributed as dist

from src.models.engines.ep_checkpoint import (
    compute_local_experts,
    extract_local_expert_state,
    merge_expert_states,
    shard_state_for_rank,
)
from src.utils.distributed import barrier_if_initialized, is_dist_initialized, print0


def build_checkpoint_payload(step, model_state, optimizers, config):
    """Create checkpoint payload with stable schema."""
    return {
        "step": step,
        "model_state_dict": model_state,
        "optimizer_state_dicts": [opt.state_dict() for opt in optimizers],
        "config": config.to_dict(),
    }


def load_checkpoint(path: str, map_location="cpu"):
    """Load checkpoint and validate required keys."""
    checkpoint = torch.load(path, map_location=map_location)
    if "config" not in checkpoint:
        raise ValueError("Checkpoint missing config")
    return checkpoint


def shard_model_state_for_ep_eval(state_dict, model_cfg, rank: int, world_size: int):
    """Shard full expert-key checkpoint state for EP eval rank."""
    return shard_state_for_rank(
        state_dict=state_dict,
        model_cfg=model_cfg,
        rank=rank,
        world_size=world_size,
    )


def save_checkpoint(output_dir, step, model, optimizers, config, expert_parallel: bool = False):
    """Save checkpoint. In EP mode gathers expert shards and writes full state on rank 0."""
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    if expert_parallel and is_dist_initialized():
        rank = dist.get_rank()
        world_size = dist.get_world_size()

        local_expert_state = extract_local_expert_state(model)
        gathered = [None] * world_size if rank == 0 else None
        dist.gather_object(local_expert_state, gathered, dst=0)

        if rank == 0:
            local_experts = compute_local_experts(config.model, world_size)
            model_state = merge_expert_states(
                base_state=model.state_dict(),
                gathered=gathered,
                local_experts=local_experts,
                world_size=world_size,
            )
            checkpoint = build_checkpoint_payload(step, model_state, optimizers, config)
            checkpoint_path = checkpoint_dir / f"checkpoint_step_{step}.pt"
            torch.save(checkpoint, checkpoint_path)
            print0(f"Saved (EP full model): {checkpoint_path}")

        barrier_if_initialized()
        return

    checkpoint = build_checkpoint_payload(step, model.state_dict(), optimizers, config)
    checkpoint_path = checkpoint_dir / f"checkpoint_step_{step}.pt"
    torch.save(checkpoint, checkpoint_path)
    print0(f"Saved: {checkpoint_path}")
