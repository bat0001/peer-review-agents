#!/usr/bin/env python3
"""Standalone CORE eval entrypoint (Hydra)."""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

import hydra
from omegaconf import DictConfig, OmegaConf
import torch
import torch.distributed as dist

from src.config import Config
from src.eval.core import evaluate_model
from src.models import BaseGPT, ModelConfig
from src.tokenizer import get_tokenizer
from src.utils.distributed import compute_init, compute_cleanup, print0


def _shard_expert_state_dict(state_dict, model_config, rank: int, world_size: int):
    model_type = model_config.model_type
    n_routed_experts = model_config.n_experts - 1 if "shared" in model_type else model_config.n_experts
    if n_routed_experts % world_size != 0:
        raise ValueError("n_routed_experts must be divisible by world_size for EP")
    local_experts = n_routed_experts // world_size
    start = rank * local_experts
    end = start + local_experts

    sharded = {}
    for key, value in state_dict.items():
        if ".expert_weight1." in key or ".expert_weight2." in key:
            prefix, idx_str = key.rsplit(".", 1)
            global_idx = int(idx_str)
            if start <= global_idx < end:
                local_idx = global_idx - start
                new_key = f"{prefix}.{local_idx}"
                sharded[new_key] = value
            continue
        sharded[key] = value
    return sharded


def load_checkpoint_model(checkpoint_path: str, device: torch.device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if "config" not in checkpoint:
        raise ValueError("Checkpoint missing config")

    config = Config.from_dict(checkpoint["config"])
    tokenizer = get_tokenizer(config.data.tokenizer_dir)
    config.model["vocab_size"] = tokenizer.get_vocab_size()

    expert_parallel = config.model.get("expert_parallel", False)
    if expert_parallel and not dist.is_initialized():
        raise RuntimeError("expert_parallel requires torchrun (distributed init)")

    model_config = ModelConfig(**config.model)
    model = BaseGPT(model_config)

    state_dict = checkpoint["model_state_dict"]
    if expert_parallel:
        state_dict = _shard_expert_state_dict(
            state_dict,
            model_config,
            rank=dist.get_rank(),
            world_size=dist.get_world_size(),
        )

    model.load_state_dict(state_dict, strict=True)
    model.to(device)
    model.eval()
    return model, tokenizer, config


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    config_dict = OmegaConf.to_container(cfg, resolve=True)
    config = Config.from_dict(config_dict)

    if not config.eval.core_checkpoint_path:
        raise ValueError("eval.core_checkpoint_path must be set")
    if not Path(config.eval.core_checkpoint_path).exists():
        raise FileNotFoundError(f"Checkpoint not found: {config.eval.core_checkpoint_path}")

    ddp, rank, local_rank, world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=config.model.get("expert_parallel", False),
    )

    try:
        model, tokenizer, _ = load_checkpoint_model(config.eval.core_checkpoint_path, device)

        autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
        with autocast_ctx:
            out = evaluate_model(
                model=model,
                tokenizer=tokenizer,
                device=device,
                max_per_task=config.eval.core_metric_max_per_task,
                eval_examples_per_forward=config.eval.core_eval_examples_per_forward,
                bundle_url=config.eval.core_bundle_url,
                bundle_dir=config.eval.core_bundle_dir,
            )

        if rank == 0:
            print0("=" * 80)
            print0(f"Checkpoint: {config.eval.core_checkpoint_path}")
            print0("=" * 80)
            for label, accuracy in out["results"].items():
                centered = out["centered_results"][label]
                print0(f"{label:<35} acc={accuracy:<10.6f} centered={centered:<10.6f}")
            print0(f"CORE{'':<31} {out['core_metric']:<10.6f}")

    finally:
        compute_cleanup()


if __name__ == "__main__":
    main()
