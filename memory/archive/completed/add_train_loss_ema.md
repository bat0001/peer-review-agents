# Plan: Add train_loss_ema Metric (Unbiased EMA 0.999)

## Goal
Add a new `train_loss_ema` metric to training logs/graphs in `train.py`. The metric should be an **unbiased (debiased) EMA** of the per-step `total_loss` using decay `0.999`, and it should appear under the `train/` group in W&B.

## Files to Change
- `train.py`
- `src/utils/metrics_organizer.py`

## Current Context (Relevant Snippet)
```python
    # Logging
    output_dir = Path(config.output_dir) / config.experiment_name
    if master_process:
        output_dir.mkdir(parents=True, exist_ok=True)

    logger = Logger(config=config.logging, output_dir=output_dir, rank=rank)
    metrics_tracker = MetricsTracker()
```

```python
    for step in range(max_steps):
        t0 = time.time()
        ...
        model.train()
        total_loss = 0.0
        routing_metrics = {}
        ...
        step_metrics = {
            'loss': total_loss,
            'learning_rate': lrm * matrix_lr,
            'throughput': throughput,
            'step_time': step_time,
            'grad_norm': grad_norm.item() if hasattr(grad_norm, 'item') else grad_norm,
            **routing_metrics,
        }
```

## Planned Changes (Detailed)
1. **Initialize EMA state before the training loop** so it persists across steps:
   - `train_loss_ema = 0.0` (float accumulator)
   - `train_loss_ema_beta = 0.999` (decay)

2. **Update EMA after each step’s `total_loss` is computed** (after gradient accumulation and before logging):
   - `train_loss_ema = beta * train_loss_ema + (1 - beta) * total_loss`
   - Debias via `train_loss_ema_unbiased = train_loss_ema / (1 - beta ** (step + 1))`

3. **Log the debiased EMA** in `step_metrics`:
   - Add `'train_loss_ema': train_loss_ema_unbiased`
   - Keep it as a Python float (no tensors) to match the logging pipeline’s deadlock-safe requirements.

4. **Map `train_loss_ema` into W&B’s `train/` namespace**:
   - In `MetricsOrganizer._map_metric`, add a rule to return `"train/loss_ema"` for `train_loss_ema`.

## Patch Sketch (Proposed Code)
```python
    # Logging
    output_dir = Path(config.output_dir) / config.experiment_name
    if master_process:
        output_dir.mkdir(parents=True, exist_ok=True)

    logger = Logger(config=config.logging, output_dir=output_dir, rank=rank)
    metrics_tracker = MetricsTracker()

    train_loss_ema = 0.0
    train_loss_ema_beta = 0.999
```

```python
        # After grad accumulation
        train_loss_ema = (
            train_loss_ema_beta * train_loss_ema
            + (1.0 - train_loss_ema_beta) * total_loss
        )
        train_loss_ema_unbiased = train_loss_ema / (
            1.0 - train_loss_ema_beta ** (step + 1)
        )

        step_metrics = {
            'loss': total_loss,
            'train_loss_ema': train_loss_ema_unbiased,
            'learning_rate': lrm * matrix_lr,
            'throughput': throughput,
            'step_time': step_time,
            'grad_norm': grad_norm.item() if hasattr(grad_norm, 'item') else grad_norm,
            **routing_metrics,
        }
```

```python
        if key == "loss":
            if not eval_prefix:
                return "train/loss"
            else:
                return "eval/loss"
        if key == "train_loss_ema":
            return "train/loss_ema"
        if key == "learning_rate":
            return "train/lr"
```

## Validation Notes
- Confirm `train_loss_ema` appears in console logs and `metrics.jsonl`.
- If `wandb` is enabled, the new graph should appear as `train/loss_ema`.
