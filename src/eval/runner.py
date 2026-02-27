"""Training/eval orchestration helpers for validation and CORE metrics."""

from src.eval.core import evaluate_model as evaluate_core_model
from src.eval.val_loss import run_val_eval
from src.utils.distributed import barrier_if_initialized, is_dist_initialized, print0


def run_core_eval(model, tokenizer, device, eval_config, autocast_ctx):
    """Run CORE evaluation with config-provided parameters."""
    with autocast_ctx:
        return evaluate_core_model(
            model=model,
            tokenizer=tokenizer,
            device=device,
            max_per_task=eval_config.core_metric_max_per_task,
            eval_examples_per_forward=eval_config.core_eval_examples_per_forward,
            bundle_url=eval_config.core_bundle_url,
            bundle_dir=eval_config.core_bundle_dir,
        )


def maybe_run_val_eval(
    step: int,
    *,
    is_final: bool,
    model,
    build_val_loader,
    config,
    logger,
    master_process: bool,
    device,
    autocast_ctx,
    threshold_capable_model: bool,
    ema_start_steps: int,
) -> None:
    """Run periodic validation eval under current distributed semantics."""
    if is_final:
        return
    if not (step % config.training.eval_interval == 0 and step > 0):
        return

    if threshold_capable_model and step < ema_start_steps:
        print0(
            f"Skipping eval at step {step}: cutoff EMA calibration starts at step {ema_start_steps}"
        )
        return

    if is_dist_initialized():
        run_val_eval(
            model=model,
            build_val_loader=build_val_loader,
            config=config,
            logger=logger if master_process else None,
            step=step,
            device=device,
            autocast_ctx=autocast_ctx,
        )
        barrier_if_initialized()
        return

    if master_process:
        run_val_eval(
            model=model,
            build_val_loader=build_val_loader,
            config=config,
            logger=logger,
            step=step,
            device=device,
            autocast_ctx=autocast_ctx,
        )


def maybe_run_core_eval(
    step: int,
    *,
    is_final: bool,
    model,
    tokenizer,
    config,
    logger,
    master_process: bool,
    device,
    autocast_ctx,
    threshold_capable_model: bool,
    ema_start_steps: int,
):
    """Run periodic/final CORE eval under current distributed semantics."""
    if config.eval.core_metric_every <= 0:
        return None
    if not is_final and not (step % config.eval.core_metric_every == 0 and step > 0):
        return None

    if threshold_capable_model and step < ema_start_steps:
        if is_final:
            print0(
                f"Skipping final CORE eval at step {step}: cutoff EMA calibration starts at step {ema_start_steps}"
            )
        else:
            print0(
                f"Skipping CORE eval at step {step}: cutoff EMA calibration starts at step {ema_start_steps}"
            )
        return None

    if is_dist_initialized():
        if is_final:
            barrier_if_initialized()
        core_out = run_core_eval(
            model=model,
            tokenizer=tokenizer,
            device=device,
            eval_config=config.eval,
            autocast_ctx=autocast_ctx,
        )
        if master_process and logger is not None:
            logger.log_metrics(step, {"metric": core_out["core_metric"]}, prefix="core/")
        barrier_if_initialized()
        return core_out

    if master_process:
        core_out = run_core_eval(
            model=model,
            tokenizer=tokenizer,
            device=device,
            eval_config=config.eval,
            autocast_ctx=autocast_ctx,
        )
        if logger is not None:
            logger.log_metrics(step, {"metric": core_out["core_metric"]}, prefix="core/")
        return core_out

    return None
