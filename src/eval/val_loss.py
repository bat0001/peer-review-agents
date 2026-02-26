"""Validation loss evaluation utilities."""

from __future__ import annotations

from typing import Callable

import torch
import torch.distributed as dist

from src.utils.distributed import print0, reduce_mean_list, reduce_mean_scalar


def compute_eval_steps(config, world_size: int) -> int:
    tokens_per_step = config.training.per_device_batch_size * config.training.sequence_length
    world_tokens_per_step = tokens_per_step * world_size
    if config.training.eval_tokens % world_tokens_per_step != 0:
        raise ValueError(
            "eval_tokens must be divisible by per-step token count "
            f"({config.training.eval_tokens} vs {world_tokens_per_step})"
        )
    return config.training.eval_tokens // world_tokens_per_step


def run_val_eval(
    model,
    build_val_loader: Callable[[], object],
    config,
    logger,
    step: int,
    device: torch.device,
    autocast_ctx,
) -> None:
    was_training = model.training
    model.eval()

    world_size = dist.get_world_size() if dist.is_initialized() else 1
    eval_steps = compute_eval_steps(config, world_size)

    val_loader = build_val_loader()
    total_loss = 0.0
    eval_metrics: dict[str, float | list[float]] = {}

    with torch.no_grad():
        for _ in range(eval_steps):
            x, y = next(val_loader)
            with autocast_ctx:
                output = model(x, y)

            total_loss += output.loss.item()

            for key, value in output.metrics.items():
                if key not in eval_metrics:
                    eval_metrics[key] = [0.0] * len(value) if isinstance(value, list) else 0.0

                if isinstance(value, list):
                    eval_metrics[key] = [
                        acc + val / eval_steps
                        for acc, val in zip(eval_metrics[key], value)
                    ]
                else:
                    eval_metrics[key] += value / eval_steps

    eval_loss = total_loss / eval_steps
    if dist.is_initialized():
        eval_loss = reduce_mean_scalar(eval_loss, device)
        for key, value in eval_metrics.items():
            if isinstance(value, list):
                eval_metrics[key] = reduce_mean_list(value, device)
            else:
                eval_metrics[key] = reduce_mean_scalar(value, device)

    eval_metrics["eval_loss"] = eval_loss

    if logger is not None:
        logger.log_metrics(step, eval_metrics, prefix="eval/")
        print0(f"  Eval Loss: {eval_loss:.4f}")

    if was_training:
        model.train()
