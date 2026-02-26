#!/usr/bin/env python3
"""Main training script with Hydra and a nanochat-style direct training loop.

Provenance:
- Adapted from nanochat training recipes:
  https://github.com/karpathy/nanochat
- Then extended for GEC/EC routing, expert-parallel flows, and CORE eval integration.
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

import hydra
from omegaconf import DictConfig, OmegaConf
import torch

from src.config import Config
from src.models import BaseGPT, ModelConfig
from src.data_loader import create_data_loader
from src.eval.core import evaluate_model as evaluate_core_model
from src.eval.val_loss import run_val_eval
from src.optimizers import create_hybrid_optimizer
from src.tokenizer import get_tokenizer
from src.utils.distributed import compute_init, compute_cleanup, init_model_weights, print0
from src.utils import Logger, MetricsTracker


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    """
    Main training entry point with Hydra.

    Usage examples:
        # Use defaults
        python train.py

        # Override config groups
        python train.py model_size=medium mlp=dense +experiment=debug

        # Multi-GPU
        torchrun --nproc_per_node=2 train.py
    """
    # Convert DictConfig to Config dataclass for validation
    config_dict = OmegaConf.to_container(cfg, resolve=True)
    config = Config.from_dict(config_dict)

    # Validate configuration
    config.validate()

    # Detect EP mode from model config
    expert_parallel = config.model.get('expert_parallel', False)

    # Initialize compute environment (EP mode uses rank-specific seeds)
    ddp, rank, local_rank, world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=expert_parallel
    )

    # Print resolved config (only on rank 0)
    if rank == 0:
        print("=" * 80)
        print("Resolved Configuration:")
        print("=" * 80)
        print(OmegaConf.to_yaml(cfg))
        print("=" * 80)

    try:
        train(config, ddp, rank, local_rank, world_size, device, expert_parallel)
    finally:
        compute_cleanup()


def train(config, ddp, rank, local_rank, world_size, device, expert_parallel=False):
    """Direct training loop (nanochat style)."""

    master_process = rank == 0

    # =========================================================================
    # SETUP
    # =========================================================================

    # Tokenizer (used for vocab size + CORE eval)
    tokenizer = get_tokenizer(config.data.tokenizer_dir)
    config.model["vocab_size"] = tokenizer.get_vocab_size()

    # Model
    model_config = ModelConfig(**config.model)
    # Pass threshold_warmup_steps from training config to model config
    model_config.threshold_warmup_steps = config.training.threshold_warmup_steps
    threshold_capable_models = {"gec", "gec_shared", "gec_shared_capacity", "ec_shared"}
    threshold_capable_model = model_config.model_type in threshold_capable_models

    # Create model on meta device for faster init (nanochat style)
    with torch.device("meta"):
        model = BaseGPT(model_config)
    model.to_empty(device=device)
    init_model_weights(model, expert_parallel=expert_parallel)  # Unified init for DP/EP

    # Verify initialization (debug mode only)
    if not config.training.compile_model:
        with torch.no_grad():
            # Check that weights are initialized (not NaN/Inf)
            for name, param in model.named_parameters():
                assert torch.isfinite(param).all(), \
                    f"Parameter {name} contains NaN/Inf after init!"
        print0("✓ Weight initialization verified")

    orig_model = model  # Keep reference for checkpointing

    # Compile (NO DDP wrapper! - nanochat style)
    if config.training.compile_model:
        model = torch.compile(model, dynamic=False)
        print0("Model compiled")

    num_params = sum(p.numel() for p in orig_model.parameters())
    print0(f"Parameters: {num_params:,}")

    # Data
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

    build_val_loader = lambda: create_data_loader(
        data_path=config.data.data_path,
        batch_size=config.training.per_device_batch_size,
        seq_len=config.training.sequence_length,
        tokenizer_dir=config.data.tokenizer_dir,
        tokenizer_threads=config.data.tokenizer_threads,
        tokenizer_batch_size=config.data.tokenizer_batch_size,
        split="val",
        device=device,
    )

    # Get optimizer config with defaults
    opt_config = getattr(config, 'optimizer', {})
    if isinstance(opt_config, dict):
        unembedding_lr = opt_config.get('unembedding_lr', 0.004)
        embedding_lr = opt_config.get('embedding_lr', 0.2)
        matrix_lr = opt_config.get('matrix_lr', 0.02)
        warmup_ratio = opt_config.get('warmup_ratio', 0.0)
        warmdown_ratio = opt_config.get('warmdown_ratio', 0.2)
        final_lr_frac = opt_config.get('final_lr_frac', 0.0)
        weight_decay = opt_config.get('weight_decay', 0.0)
    else:
        # Use defaults if no optimizer config
        unembedding_lr = 0.004
        embedding_lr = 0.2
        matrix_lr = 0.02
        warmup_ratio = 0.0
        warmdown_ratio = 0.2
        final_lr_frac = 0.0
        weight_decay = 0.0

    # Optimizers (Hybrid: AdamW + Muon, + EP local Muon if expert_parallel)
    opt_result = create_hybrid_optimizer(
        model=orig_model,
        unembedding_lr=unembedding_lr,
        embedding_lr=embedding_lr,
        matrix_lr=matrix_lr,
        weight_decay=weight_decay,
        model_dim=model_config.n_embd,
        use_dist=ddp,
        expert_parallel=expert_parallel,
    )

    if expert_parallel and len(opt_result) == 3:
        adamw_optimizer, muon_optimizer, expert_optimizer = opt_result
        optimizers = [adamw_optimizer, muon_optimizer, expert_optimizer]
        print0(f"Optimizers created: AdamW (embeddings), Muon (matrices), Local Muon (EP experts)")
    else:
        adamw_optimizer, muon_optimizer = opt_result
        optimizers = [adamw_optimizer, muon_optimizer]
        print0(f"Optimizers created: AdamW (embeddings), Muon (matrices)")

    # LR schedule (nanochat style: constant + warmdown)
    max_steps = config.training.calculate_max_steps()
    total_tokens = max_steps * config.training.total_batch_size
    print0(f"Training for {max_steps:,} steps ({total_tokens/1e9:.2f}B tokens)")

    def get_lr_multiplier(it):
        """LR schedule: warmup (if any) → constant → warmdown."""
        warmup_iters = round(warmup_ratio * max_steps)
        warmdown_iters = round(warmdown_ratio * max_steps)
        if it < warmup_iters:
            return (it + 1) / warmup_iters if warmup_iters > 0 else 1.0
        elif it <= max_steps - warmdown_iters:
            return 1.0  # Constant!
        else:
            progress = (max_steps - it) / warmdown_iters
            return progress * 1.0 + (1 - progress) * final_lr_frac

    # Muon momentum schedule
    def get_muon_momentum(it):
        """Muon momentum: 0.85 → 0.95 over first 300 steps."""
        frac = min(it / 300, 1)
        return (1 - frac) * 0.85 + frac * 0.95

    # Logging
    output_dir = Path(config.output_dir) / config.experiment_name
    if master_process:
        output_dir.mkdir(parents=True, exist_ok=True)

    logger = Logger(config=config.logging, output_dir=output_dir, rank=rank)
    metrics_tracker = MetricsTracker()

    # Mixed precision
    autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)

    # =========================================================================
    # TRAINING LOOP (nanochat direct style)
    # =========================================================================

    print0(f"\nStarting training for {max_steps} steps...\n")

    ema_start_steps = config.training.ema_start_steps
    threshold_warmup_steps = config.training.threshold_warmup_steps

    if threshold_capable_model:
        print0(f"Cutoff EMA updates start at step {ema_start_steps}")
        # Threshold warmup enabled (switch to threshold at configured step)
        if threshold_warmup_steps >= 0:
            print0(f"Threshold training enabled: switching to threshold at step {threshold_warmup_steps}")
    else:
        if ema_start_steps != 0 or threshold_warmup_steps != -1:
            print0(
                f"Ignoring ema_start_steps={ema_start_steps} and "
                f"threshold_warmup_steps={threshold_warmup_steps} for model_type={model_config.model_type}"
            )

    # Loss EMA tracking (unbiased)
    loss_ema = 0.0
    loss_ema_decay = 0.999

    # Prefetch first batch
    x, y = next(data_loader)

    # Barrier before training loop
    import torch.distributed as dist
    if dist.is_initialized():
        dist.barrier()

    for step in range(max_steps):
        t0 = time.time()

        # Check for threshold mode switch
        if threshold_capable_model and step == threshold_warmup_steps and threshold_warmup_steps >= 0:
            # Print cutoff_ema values before switching (debug)
            # NOTE: All ranks must call .item() to avoid deadlock (GPU sync)
            for i, block in enumerate(orig_model.blocks):
                if hasattr(block.mlp, 'cutoff_ema'):
                    cutoff_mean = block.mlp.cutoff_ema.mean().item()
                    cutoff_max = block.mlp.cutoff_ema.max().item()
                    if rank == 0:
                        print0(f"  Layer {i}: cutoff_ema mean={cutoff_mean:.4f}, max={cutoff_max:.4f}")
                    break  # Just show first layer

            orig_model.set_routing_mode('threshold')
            print0(f"→ Switched to threshold routing at step {step}")

        # Update learning rates
        lrm = get_lr_multiplier(step)
        for opt in optimizers:
            for group in opt.param_groups:
                group['lr'] = group['initial_lr'] * lrm

        # Update Muon momentum
        muon_momentum = get_muon_momentum(step)
        for group in muon_optimizer.param_groups:
            group['momentum'] = muon_momentum

        # Forward/backward with gradient accumulation
        model.train()
        total_loss = 0.0
        routing_metrics = {}  # Accumulate routing metrics across micro-steps (now Python scalars/lists)

        for micro_step in range(grad_accum_steps):
            with autocast_ctx:
                output = model(x, y)
                loss = output.loss / grad_accum_steps

            total_loss += loss.item()

            # Assert: Model returned scalar metrics (defense in depth)
            for k, v in output.metrics.items():
                assert not torch.is_tensor(v), \
                    f"BUG: Model returned tensor metric '{k}'. " \
                    f"Passing tensor-type metrics risks deadlocks. " \
                    f"ModelBase.forward() should convert all metrics to Python types."

            # Accumulate routing metrics (simple Python arithmetic)
            for k, v in output.metrics.items():
                if k not in routing_metrics:
                    # Initialize based on type
                    if isinstance(v, list):
                        routing_metrics[k] = [0.0] * len(v)
                    else:
                        routing_metrics[k] = 0.0

                # Accumulate with type checking
                if isinstance(v, list):
                    # Vector metric: element-wise accumulation
                    assert isinstance(routing_metrics[k], list), \
                        f"Metric '{k}' type changed (was list, now {type(routing_metrics[k])})"
                    assert len(v) == len(routing_metrics[k]), \
                        f"Metric '{k}' length mismatch: {len(v)} vs {len(routing_metrics[k])}"

                    routing_metrics[k] = [
                        acc + val / grad_accum_steps
                        for acc, val in zip(routing_metrics[k], v)
                    ]
                else:
                    # Scalar metric: simple addition
                    assert not isinstance(routing_metrics[k], list), \
                        f"Metric '{k}' type changed (was scalar, now list)"
                    routing_metrics[k] += v / grad_accum_steps

            loss.backward()

            # Prefetch next batch while GPU busy
            x, y = next(data_loader)

        # Update loss EMA (unbiased)
        loss_ema = loss_ema_decay * loss_ema + (1 - loss_ema_decay) * total_loss
        bias_correction = 1 - loss_ema_decay ** (step + 1)
        train_loss_ema = loss_ema / bias_correction

        # Gradient clipping
        if config.training.grad_clip > 0:
            grad_norm = torch.nn.utils.clip_grad_norm_(
                orig_model.parameters(),
                config.training.grad_clip
            )
        else:
            grad_norm = 0.0

        # Optimizer step (both optimizers)
        for opt in optimizers:
            opt.step()

        orig_model.zero_grad(set_to_none=True)

        # Complete training step (finalize accumulation, sync if needed)
        orig_model.step_complete(
            step=step,
            ema_start_steps=ema_start_steps,
            threshold_warmup_steps=threshold_warmup_steps,
            threshold_capable=threshold_capable_model,
        )

        torch.cuda.synchronize()
        t1 = time.time()

        # Logging
        step_time = t1 - t0
        tokens_per_step = config.training.total_batch_size
        throughput = tokens_per_step / step_time

        step_metrics = {
            'loss': total_loss,
            'train_loss_ema': train_loss_ema,
            'learning_rate': lrm * matrix_lr,
            'throughput': throughput,
            'step_time': step_time,
            'grad_norm': grad_norm.item() if hasattr(grad_norm, 'item') else grad_norm,
            **routing_metrics,  # Already Python types from ModelBase!
        }

        # Assert: No tensors before logging (defense in depth)
        for k, v in step_metrics.items():
            assert not torch.is_tensor(v), \
                f"Tensor '{k}' in step_metrics! Passing tensor-type metrics risks deadlocks."
            assert isinstance(v, (int, float, list, bool)), \
                f"Unexpected type for metric '{k}': {type(v)}"

        if step % config.logging.log_interval == 0:
            if master_process:
                logger.log_metrics(step, step_metrics)

            # Barrier after logging to ensure all ranks sync before continuing
            import torch.distributed as dist
            if dist.is_initialized():
                dist.barrier()

        # Evaluation
        if step % config.training.eval_interval == 0 and step > 0:
            if threshold_capable_model and step < ema_start_steps:
                print0(
                    f"Skipping eval at step {step}: cutoff EMA calibration starts at step {ema_start_steps}"
                )
            else:
                import torch.distributed as dist
                if dist.is_initialized():
                    run_val_eval(
                        model=model,
                        build_val_loader=build_val_loader,
                        config=config,
                        logger=logger if master_process else None,
                        step=step,
                        device=device,
                        autocast_ctx=autocast_ctx,
                    )
                    dist.barrier()
                elif master_process:
                    run_val_eval(
                        model=model,
                        build_val_loader=build_val_loader,
                        config=config,
                        logger=logger,
                        step=step,
                        device=device,
                        autocast_ctx=autocast_ctx,
                    )

        # CORE metric evaluation (all ranks if distributed)
        if config.eval.core_metric_every > 0 and step % config.eval.core_metric_every == 0 and step > 0:
            if threshold_capable_model and step < ema_start_steps:
                print0(
                    f"Skipping CORE eval at step {step}: cutoff EMA calibration starts at step {ema_start_steps}"
                )
            else:
                import torch.distributed as dist
                core_model = orig_model if config.training.compile_model else model
                if dist.is_initialized():
                    with autocast_ctx:
                        core_out = evaluate_core_model(
                            model=core_model,
                            tokenizer=tokenizer,
                            device=device,
                            max_per_task=config.eval.core_metric_max_per_task,
                            bundle_url=config.eval.core_bundle_url,
                            bundle_dir=config.eval.core_bundle_dir,
                        )
                    if master_process:
                        logger.log_metrics(step, {"metric": core_out["core_metric"]}, prefix="core/")
                    dist.barrier()
                elif master_process:
                    with autocast_ctx:
                        core_out = evaluate_core_model(
                            model=core_model,
                            tokenizer=tokenizer,
                            device=device,
                            max_per_task=config.eval.core_metric_max_per_task,
                            bundle_url=config.eval.core_bundle_url,
                            bundle_dir=config.eval.core_bundle_dir,
                        )
                    logger.log_metrics(step, {"metric": core_out["core_metric"]}, prefix="core/")

        # Checkpointing (EP mode requires all ranks for gather)
        if step % config.training.save_interval == 0 and step > 0:
            if expert_parallel:
                # EP: all ranks participate in gather, rank 0 saves
                save_checkpoint(output_dir, step, orig_model, optimizers, config, expert_parallel=True)
            elif master_process:
                save_checkpoint(output_dir, step, orig_model, optimizers, config)

    # Final checkpoint
    if expert_parallel:
        save_checkpoint(output_dir, max_steps, orig_model, optimizers, config, expert_parallel=True)
    elif master_process:
        save_checkpoint(output_dir, max_steps, orig_model, optimizers, config)

    # Final CORE metric evaluation (after training)
    if config.eval.core_metric_every > 0:
        if threshold_capable_model and max_steps < ema_start_steps:
            print0(
                f"Skipping final CORE eval at step {max_steps}: cutoff EMA calibration starts at step {ema_start_steps}"
            )
        else:
            import torch.distributed as dist
            core_model = orig_model if config.training.compile_model else model
            if dist.is_initialized():
                dist.barrier()
                with autocast_ctx:
                    core_out = evaluate_core_model(
                        model=core_model,
                        tokenizer=tokenizer,
                        device=device,
                        max_per_task=config.eval.core_metric_max_per_task,
                        bundle_url=config.eval.core_bundle_url,
                        bundle_dir=config.eval.core_bundle_dir,
                    )
                if master_process:
                    logger.log_metrics(max_steps, {"metric": core_out["core_metric"]}, prefix="core/")
                dist.barrier()
            elif master_process:
                with autocast_ctx:
                    core_out = evaluate_core_model(
                        model=core_model,
                        tokenizer=tokenizer,
                        device=device,
                        max_per_task=config.eval.core_metric_max_per_task,
                        bundle_url=config.eval.core_bundle_url,
                        bundle_dir=config.eval.core_bundle_dir,
                    )
                logger.log_metrics(max_steps, {"metric": core_out["core_metric"]}, prefix="core/")

    print0("\nTraining complete!")


def save_checkpoint(output_dir, step, model, optimizers, config, expert_parallel=False):
    """Save checkpoint.

    For EP mode, gathers expert weights from all ranks to save a full model.
    """
    import torch.distributed as dist
    import re

    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)

    if expert_parallel and dist.is_initialized():
        # EP mode: gather expert shards to rank 0, save full model
        rank = dist.get_rank()
        world_size = dist.get_world_size()

        # 1. Extract local expert state
        local_expert_state = {
            name: param.data.cpu()
            for name, param in model.named_parameters()
            if 'expert_weight' in name
        }

        # 2. Gather all shards to rank 0
        gathered = [None] * world_size
        dist.gather_object(local_expert_state, gathered if rank == 0 else None, dst=0)

        if rank == 0:
            # 3. Build full model state
            model_state = model.state_dict()

            # Remove local expert params (will replace with full)
            expert_keys = [k for k in model_state.keys() if 'expert_weight' in k]
            for k in expert_keys:
                del model_state[k]

            # Compute local experts per rank from config (not from key count across layers)
            model_cfg = config.model
            model_type = model_cfg.get("model_type", "")
            n_experts = model_cfg.get("n_experts")
            if n_experts is None:
                G = model_cfg.get("granularity")
                E = model_cfg.get("expansion")
                if G is None or E is None:
                    raise ValueError("Missing granularity/expansion for EP checkpoint save")
                n_experts = int(G) * int(E)
                if "shared" in model_type:
                    n_experts += 1
            n_routed_experts = n_experts - 1 if "shared" in model_type else n_experts
            if n_routed_experts % world_size != 0:
                raise ValueError(
                    f"n_routed_experts ({n_routed_experts}) must be divisible by world_size ({world_size}) for EP"
                )
            local_experts = n_routed_experts // world_size

            # Helper to extract expert index from param name
            def extract_expert_idx(name, r):
                # Name like "blocks.0.mlp.engine.expert_weight1.0"
                # Local index is the last number, global = r * local_experts + local_idx
                match = re.search(r'\.(\d+)$', name)
                if match:
                    local_idx = int(match.group(1))
                    return r * local_experts + local_idx
                return 0

            # 4. Merge expert shards by layer and weight type
            # Group by layer path (e.g., "blocks.0.mlp.engine")
            layer_experts = {}
            for r in range(world_size):
                for name, tensor in gathered[r].items():
                    # Extract layer path and weight type
                    # e.g., "blocks.0.mlp.engine.expert_weight1.0" -> ("blocks.0.mlp.engine", "expert_weight1", 0)
                    parts = name.rsplit('.', 2)
                    if len(parts) == 3:
                        layer_path, weight_type, local_idx = parts
                        key = (layer_path, weight_type)
                        if key not in layer_experts:
                            layer_experts[key] = []
                        global_idx = extract_expert_idx(name, r)
                        layer_experts[key].append((global_idx, tensor))

            # Sort and add to model_state with correct global indices
            for (layer_path, weight_type), experts in layer_experts.items():
                experts.sort(key=lambda x: x[0])
                for global_idx, tensor in experts:
                    full_name = f"{layer_path}.{weight_type}.{global_idx}"
                    model_state[full_name] = tensor

            checkpoint = {
                'step': step,
                'model_state_dict': model_state,  # Full model!
                'optimizer_state_dicts': [opt.state_dict() for opt in optimizers],
                'config': config.to_dict(),
            }

            checkpoint_path = checkpoint_dir / f"checkpoint_step_{step}.pt"
            torch.save(checkpoint, checkpoint_path)
            print0(f"Saved (EP full model): {checkpoint_path}")

        # Barrier to ensure all ranks wait for save to complete
        dist.barrier()
    else:
        # Standard mode: save directly
        checkpoint = {
            'step': step,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dicts': [opt.state_dict() for opt in optimizers],
            'config': config.to_dict(),
        }

        checkpoint_path = checkpoint_dir / f"checkpoint_step_{step}.pt"
        torch.save(checkpoint, checkpoint_path)
        print0(f"Saved: {checkpoint_path}")


if __name__ == "__main__":
    main()
