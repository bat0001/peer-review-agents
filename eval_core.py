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
from src.eval.runner import run_core_eval
from src.models import BaseGPT, ModelConfig
from src.tokenizer import get_tokenizer
from src.utils.checkpoint import load_checkpoint, shard_model_state_for_ep_eval
from src.utils.distributed import compute_cleanup, compute_init, print0


def load_checkpoint_model(checkpoint_path: str, device: torch.device):
    checkpoint = load_checkpoint(checkpoint_path, map_location="cpu")

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
        state_dict = shard_model_state_for_ep_eval(
            state_dict=state_dict,
            model_cfg=config.model,
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

    _ddp, rank, _local_rank, _world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=config.model.get("expert_parallel", False),
    )

    try:
        model, tokenizer, _ = load_checkpoint_model(config.eval.core_checkpoint_path, device)

        autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
        out = run_core_eval(
            model=model,
            tokenizer=tokenizer,
            device=device,
            eval_config=config.eval,
            autocast_ctx=autocast_ctx,
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
