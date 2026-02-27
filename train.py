#!/usr/bin/env python3
"""Main training script with Hydra and a nanochat-style direct training loop."""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

import hydra
from omegaconf import DictConfig, OmegaConf
import torch

from src.config import Config
from src.data_loader import create_data_loader
from src.eval.runner import maybe_run_core_eval, maybe_run_val_eval
from src.models import BaseGPT, ModelConfig
from src.optimizers import create_hybrid_optimizer
from src.optimizers.schedule import apply_lr_schedule, apply_muon_schedule
from src.tokenizer import get_tokenizer
from src.utils.checkpoint import save_checkpoint
from src.utils.distributed import (
    barrier_if_initialized,
    compute_cleanup,
    compute_init,
    init_model_weights,
    print0,
)
from src.utils.logger import Logger


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    """Main training entry point with Hydra."""
    config_dict = OmegaConf.to_container(cfg, resolve=True)
    config = Config.from_dict(config_dict)
    config.validate()

    expert_parallel = config.model.get("expert_parallel", False)

    ddp, rank, _local_rank, world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=expert_parallel,
    )

    if rank == 0:
        print("=" * 80)
        print("Resolved Configuration:")
        print("=" * 80)
        print(OmegaConf.to_yaml(cfg))
        print("=" * 80)

    try:
        train(config, ddp, rank, world_size, device, expert_parallel)
    finally:
        compute_cleanup()


def train(config, ddp, rank, world_size, device, expert_parallel: bool = False):
    """Direct training loop (nanochat style)."""
    master_process = rank == 0

    tokenizer = get_tokenizer(config.data.tokenizer_dir)
    config.model["vocab_size"] = tokenizer.get_vocab_size()

    model_config = ModelConfig(**config.model)
    model_config.threshold_warmup_steps = config.training.threshold_warmup_steps
    threshold_capable_model = model_config.model_type in {"expert_choice"}

    with torch.device("meta"):
        model = BaseGPT(model_config)
    model.to_empty(device=device)
    init_model_weights(model, expert_parallel=expert_parallel)

    if not config.training.compile_model:
        with torch.no_grad():
            for name, param in model.named_parameters():
                assert torch.isfinite(param).all(), f"Parameter {name} contains NaN/Inf after init!"
        print0("✓ Weight initialization verified")

    orig_model = model

    if config.training.compile_model:
        model = torch.compile(model, dynamic=False)
        print0("Model compiled")

    num_params = sum(p.numel() for p in orig_model.parameters())
    print0(f"Parameters: {num_params:,}")

    grad_accum_steps = config.training.validate_batch_settings(world_size)
    print0(f"Gradient accumulation: {grad_accum_steps}")
    print0(f"Total batch size: {config.training.total_batch_size} tokens")
    print0(f"Per-device batch size: {config.training.per_device_batch_size} samples")

    data_loader = create_data_loader(
        data_path=config.data.data_path,
        batch_size=config.training.per_device_batch_size,
        seq_len=config.training.sequence_length,
        tokenizer_dir=config.data.tokenizer_dir,
        tokenizer_threads=config.data.tokenizer_threads,
        tokenizer_batch_size=config.data.tokenizer_batch_size,
        split="train",
        device=device,
    )

    def build_val_loader():
        return create_data_loader(
            data_path=config.data.data_path,
            batch_size=config.training.per_device_batch_size,
            seq_len=config.training.sequence_length,
            tokenizer_dir=config.data.tokenizer_dir,
            tokenizer_threads=config.data.tokenizer_threads,
            tokenizer_batch_size=config.data.tokenizer_batch_size,
            split="val",
            device=device,
        )

    opt_config = config.optimizer
    opt_result = create_hybrid_optimizer(
        model=orig_model,
        unembedding_lr=opt_config.unembedding_lr,
        embedding_lr=opt_config.embedding_lr,
        matrix_lr=opt_config.matrix_lr,
        weight_decay=opt_config.weight_decay,
        adamw_betas=tuple(opt_config.adamw_betas),
        adamw_eps=opt_config.adamw_eps,
        muon_momentum=opt_config.muon_momentum,
        muon_nesterov=opt_config.muon_nesterov,
        muon_ns_steps=opt_config.muon_ns_steps,
        model_dim=model_config.n_embd,
        use_dist=ddp,
        expert_parallel=expert_parallel,
    )

    if expert_parallel and len(opt_result) == 3:
        adamw_optimizer, muon_optimizer, expert_optimizer = opt_result
        optimizers = [adamw_optimizer, muon_optimizer, expert_optimizer]
        print0("Optimizers created: AdamW (embeddings), Muon (matrices), Local Muon (EP experts)")
    else:
        adamw_optimizer, muon_optimizer = opt_result
        optimizers = [adamw_optimizer, muon_optimizer]
        print0("Optimizers created: AdamW (embeddings), Muon (matrices)")

    max_steps = config.training.calculate_max_steps()
    total_tokens = max_steps * config.training.total_batch_size
    print0(f"Training for {max_steps:,} steps ({total_tokens / 1e9:.2f}B tokens)")

    output_dir = Path(config.output_dir)
    if master_process:
        output_dir.mkdir(parents=True, exist_ok=True)

    logger = Logger(config=config.logging, output_dir=output_dir, rank=rank)

    autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)

    print0(f"\nStarting training for {max_steps} steps...\n")

    ema_start_steps = config.training.ema_start_steps
    threshold_warmup_steps = config.training.threshold_warmup_steps

    if threshold_capable_model:
        print0(f"Cutoff EMA updates start at step {ema_start_steps}")
        if threshold_warmup_steps >= 0:
            print0(f"Threshold training enabled: switching to threshold at step {threshold_warmup_steps}")
    elif ema_start_steps != 0 or threshold_warmup_steps != -1:
        print0(
            f"Ignoring ema_start_steps={ema_start_steps} and "
            f"threshold_warmup_steps={threshold_warmup_steps} for model_type={model_config.model_type}"
        )

    loss_ema = 0.0
    loss_ema_decay = 0.999

    x, y = next(data_loader)
    barrier_if_initialized()

    for step in range(max_steps):
        t0 = time.time()

        if threshold_capable_model and step == threshold_warmup_steps and threshold_warmup_steps >= 0:
            for i, block in enumerate(orig_model.blocks):
                if hasattr(block.mlp, "cutoff_ema"):
                    cutoff_mean = block.mlp.cutoff_ema.mean().item()
                    cutoff_max = block.mlp.cutoff_ema.max().item()
                    if rank == 0:
                        print0(f"  Layer {i}: cutoff_ema mean={cutoff_mean:.4f}, max={cutoff_max:.4f}")
                    break

            orig_model.set_routing_mode("threshold")
            print0(f"→ Switched to threshold routing at step {step}")

        lrm = apply_lr_schedule(step, max_steps, optimizers, opt_config)
        muon_momentum = apply_muon_schedule(step, muon_optimizer, opt_config)

        model.train()
        total_loss = 0.0
        routing_metrics = {}

        for _micro_step in range(grad_accum_steps):
            with autocast_ctx:
                output = model(x, y)
                loss = output.loss / grad_accum_steps

            total_loss += loss.item()

            for key, value in output.metrics.items():
                assert not torch.is_tensor(value), (
                    f"BUG: Model returned tensor metric '{key}'. "
                    "Passing tensor-type metrics risks deadlocks. "
                    "ModelBase.forward() should convert all metrics to Python types."
                )

                if key not in routing_metrics:
                    routing_metrics[key] = [0.0] * len(value) if isinstance(value, list) else 0.0

                if isinstance(value, list):
                    assert isinstance(routing_metrics[key], list), (
                        f"Metric '{key}' type changed (was list, now {type(routing_metrics[key])})"
                    )
                    assert len(value) == len(routing_metrics[key]), (
                        f"Metric '{key}' length mismatch: {len(value)} vs {len(routing_metrics[key])}"
                    )
                    routing_metrics[key] = [
                        acc + val / grad_accum_steps
                        for acc, val in zip(routing_metrics[key], value)
                    ]
                else:
                    assert not isinstance(routing_metrics[key], list), (
                        f"Metric '{key}' type changed (was scalar, now list)"
                    )
                    routing_metrics[key] += value / grad_accum_steps

            loss.backward()
            x, y = next(data_loader)

        loss_ema = loss_ema_decay * loss_ema + (1 - loss_ema_decay) * total_loss
        bias_correction = 1 - loss_ema_decay ** (step + 1)
        train_loss_ema = loss_ema / bias_correction

        if config.training.grad_clip > 0:
            grad_norm = torch.nn.utils.clip_grad_norm_(orig_model.parameters(), config.training.grad_clip)
        else:
            grad_norm = 0.0

        for opt in optimizers:
            opt.step()

        orig_model.zero_grad(set_to_none=True)

        orig_model.step_complete(
            step=step,
            ema_start_steps=ema_start_steps,
            threshold_warmup_steps=threshold_warmup_steps,
            threshold_capable=threshold_capable_model,
        )

        torch.cuda.synchronize()
        t1 = time.time()

        step_time = t1 - t0
        throughput = config.training.total_batch_size / step_time
        step_metrics = {
            "loss": total_loss,
            "train_loss_ema": train_loss_ema,
            "learning_rate": lrm * opt_config.matrix_lr,
            "muon_momentum": muon_momentum,
            "throughput": throughput,
            "step_time": step_time,
            "grad_norm": grad_norm.item() if hasattr(grad_norm, "item") else grad_norm,
            **routing_metrics,
        }

        for key, value in step_metrics.items():
            assert not torch.is_tensor(value), (
                f"Tensor '{key}' in step_metrics! Passing tensor-type metrics risks deadlocks."
            )
            assert isinstance(value, (int, float, list, bool)), (
                f"Unexpected type for metric '{key}': {type(value)}"
            )

        if step % config.logging.log_interval == 0:
            if master_process:
                logger.log_metrics(step, step_metrics)
            barrier_if_initialized()

        maybe_run_val_eval(
            step,
            is_final=False,
            model=model,
            build_val_loader=build_val_loader,
            config=config,
            logger=logger,
            master_process=master_process,
            device=device,
            autocast_ctx=autocast_ctx,
            threshold_capable_model=threshold_capable_model,
            ema_start_steps=ema_start_steps,
        )

        core_model = orig_model if config.training.compile_model else model
        maybe_run_core_eval(
            step,
            is_final=False,
            model=core_model,
            tokenizer=tokenizer,
            config=config,
            logger=logger,
            master_process=master_process,
            device=device,
            autocast_ctx=autocast_ctx,
            threshold_capable_model=threshold_capable_model,
            ema_start_steps=ema_start_steps,
        )

        if step % config.training.save_interval == 0 and step > 0:
            if expert_parallel:
                save_checkpoint(output_dir, step, orig_model, optimizers, config, expert_parallel=True)
            elif master_process:
                save_checkpoint(output_dir, step, orig_model, optimizers, config)

    if expert_parallel:
        save_checkpoint(output_dir, max_steps, orig_model, optimizers, config, expert_parallel=True)
    elif master_process:
        save_checkpoint(output_dir, max_steps, orig_model, optimizers, config)

    core_model = orig_model if config.training.compile_model else model
    maybe_run_core_eval(
        max_steps,
        is_final=True,
        model=core_model,
        tokenizer=tokenizer,
        config=config,
        logger=logger,
        master_process=master_process,
        device=device,
        autocast_ctx=autocast_ctx,
        threshold_capable_model=threshold_capable_model,
        ema_start_steps=ema_start_steps,
    )

    logger.finish()
    print0("\nTraining complete!")


if __name__ == "__main__":
    main()
