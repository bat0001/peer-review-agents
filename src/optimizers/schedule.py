"""Optimizer schedule utilities."""


def get_lr_multiplier(step: int, max_steps: int, warmup_ratio: float, warmdown_ratio: float, final_lr_frac: float) -> float:
    """LR schedule: warmup (if any) -> constant -> warmdown."""
    warmup_iters = round(warmup_ratio * max_steps)
    warmdown_iters = round(warmdown_ratio * max_steps)

    if step < warmup_iters:
        return (step + 1) / warmup_iters if warmup_iters > 0 else 1.0
    if step <= max_steps - warmdown_iters:
        return 1.0

    progress = (max_steps - step) / warmdown_iters
    return progress + (1 - progress) * final_lr_frac


def get_muon_momentum(step: int, start: float, end: float, warmup_steps: int) -> float:
    """Muon momentum schedule."""
    if warmup_steps <= 0:
        return end
    frac = min(step / warmup_steps, 1.0)
    return (1 - frac) * start + frac * end


def apply_lr_schedule(step: int, max_steps: int, optimizers, optimizer_cfg) -> float:
    """Apply LR schedule to all optimizer param groups and return multiplier."""
    lrm = get_lr_multiplier(
        step=step,
        max_steps=max_steps,
        warmup_ratio=optimizer_cfg.warmup_ratio,
        warmdown_ratio=optimizer_cfg.warmdown_ratio,
        final_lr_frac=optimizer_cfg.final_lr_frac,
    )

    for opt in optimizers:
        for group in opt.param_groups:
            group["lr"] = group["initial_lr"] * lrm

    return lrm


def apply_muon_schedule(step: int, muon_optimizer, optimizer_cfg) -> float:
    """Apply Muon momentum schedule and return momentum."""
    momentum = get_muon_momentum(
        step=step,
        start=optimizer_cfg.muon_momentum_start,
        end=optimizer_cfg.muon_momentum_end,
        warmup_steps=optimizer_cfg.muon_momentum_warmup_steps,
    )

    for group in muon_optimizer.param_groups:
        group["momentum"] = momentum

    return momentum
