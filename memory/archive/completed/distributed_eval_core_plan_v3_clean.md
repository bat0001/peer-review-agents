# Plan: Clean eval refactor (nanochat-aligned, minimal core changes)

## Intent & constraints
- **Primary goal:** clean, modular eval code (loss + CORE) with deterministic val behavior.
- **Secondary constraint:** minimize changes to core model code (no edits to `src/models/model_base.py` or MLPs).
- **Alignment target:** nanochat_updated defaults (val = last parquet shard, `eval_interval=250`, `eval_tokens=20*524288`).

## Key observations from repo + nanochat
- `train.py` eval is local-only today; EP/DP needs all ranks to run and aggregate.
- GEC routing auto-switches with `model.eval()`; no need to touch model code.
- nanochat val split: last parquet shard only (`parquet_paths[-1:]`).
- nanochat eval cadence: `eval_every=250`, `eval_tokens=20*524288`; eval steps computed from token budget and world size.
- Current repo default `eval_interval=50` (mismatch); we will update defaults to align with nanochat.

## Design (clean refactor)
1) **Move eval logic into `src/eval/`** so `train.py` stays small.
2) **Add tiny distributed mean-reduction helpers** (in `src/utils/distributed.py`).
3) **Keep core model code untouched**: eval uses `model.eval()` and `model(...)` only.
4) **Use the same CORE eval code path** for training hook and standalone script.
5) **Log only one CORE scalar** to avoid graph spam.

## File-by-file plan (detailed)

### 1) Distributed mean reduction helpers
**File:** `src/utils/distributed.py`

Add two small helpers to reduce scalar/list metrics across ranks (mean only).

```python
def reduce_mean_scalar(value: float, device: torch.device) -> float:
    if not dist.is_initialized():
        return value
    tensor = torch.tensor([value], device=device, dtype=torch.float32)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor /= dist.get_world_size()
    return float(tensor.item())


def reduce_mean_list(values: list[float], device: torch.device) -> list[float]:
    if not dist.is_initialized():
        return values
    tensor = torch.tensor(values, device=device, dtype=torch.float32)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor /= dist.get_world_size()
    return tensor.cpu().tolist()
```

### 2) Clean eval module for val loss
**New files:**
- `src/eval/__init__.py`
- `src/eval/val_loss.py`

Responsibilities:
- Build val loader per eval (deterministic reset).
- Compute eval steps from `eval_tokens` (nanochat-aligned).
- Accumulate loss + routing metrics.
- Reduce metrics across ranks (EP/DP safe).
- Log only on rank 0 (or `logger is None` pattern).

Sketch:
```python
def compute_eval_steps(config, world_size: int) -> int:
    tokens_per_step = config.training.per_device_batch_size * config.training.sequence_length
    world_tokens_per_step = tokens_per_step * world_size
    assert config.training.eval_tokens % world_tokens_per_step == 0, "eval_tokens must divide world tokens per step"
    eval_steps = config.training.eval_tokens // world_tokens_per_step
    return eval_steps


def run_val_eval(model, build_val_loader, config, logger, step, device, autocast_ctx):
    model.eval()
    val_loader = build_val_loader()
    world_size = dist.get_world_size() if dist.is_initialized() else 1
    eval_steps = compute_eval_steps(config, world_size)

    total_loss = 0.0
    eval_metrics = {}
    with torch.no_grad():
        for _ in range(eval_steps):
            x, y = next(val_loader)
            with autocast_ctx:
                output = model(x, y)
            total_loss += output.loss.item()
            # accumulate metrics as in train.py (mean across batches)
            for k, v in output.metrics.items():
                if k not in eval_metrics:
                    eval_metrics[k] = [0.0] * len(v) if isinstance(v, list) else 0.0
                if isinstance(v, list):
                    eval_metrics[k] = [
                        acc + val / eval_steps for acc, val in zip(eval_metrics[k], v)
                    ]
                else:
                    eval_metrics[k] += v / eval_steps

    eval_loss = total_loss / eval_steps
    if dist.is_initialized():
        eval_loss = reduce_mean_scalar(eval_loss, device)
        for k, v in eval_metrics.items():
            eval_metrics[k] = reduce_mean_list(v, device) if isinstance(v, list) else reduce_mean_scalar(v, device)
    eval_metrics["eval_loss"] = eval_loss

    if logger is not None:
        logger.log_metrics(step, eval_metrics, prefix="eval/")
        print0(f"  Eval Loss: {eval_loss:.4f}")
    model.train()
```

Notes:
- No changes to `model_base`; relies on `model.eval()`.

### 3) Train loop wiring (minimal + clean)
**File:** `train.py`

Replace inline `evaluate()` with `run_val_eval()` from `src/eval/val_loss.py`.
Keep train loop small and readable.

```python
from src.eval.val_loss import run_val_eval

# after train loader creation
build_val_loader = lambda: create_data_loader(
    data_path=config.data.data_path,
    batch_size=config.training.per_device_batch_size,
    seq_len=config.training.sequence_length,
    tokenizer_name=config.data.tokenizer,
    split="val",
)

# in training loop:
if step % config.training.eval_interval == 0 and step > 0:
    run_val_eval(
        model=model,
        build_val_loader=build_val_loader,
        config=config,
        logger=logger if master_process else None,
        step=step,
        device=device,
        autocast_ctx=autocast_ctx,
    )
```

Call-site note (per repo rule):
- I will `rg "evaluate(" train.py src/` and enumerate call sites before removing the old helper.

### 4) Eval token budget config (nanochat-aligned defaults)
**File:** `src/config.py`

Add `eval_tokens` to `TrainingConfig` with nanochat default.
```python
@dataclass
class TrainingConfig:
    ...
    eval_interval: int = 250  # nanochat default
    eval_tokens: int = 20 * 524288  # nanochat default
```

Update configs to stay consistent:
- `configs/experiment/debug.yaml`
- `configs/training/quick.yaml`
- `configs/training/standard.yaml`
- `configs/training/long.yaml`
- `configs/experiment/full_run.yaml` (if present)

### 5) CORE eval (single module + training hook + standalone entrypoint)
**New files:**
- `src/eval/core.py` (ported scoring + bundle + evaluate_model).
- `script/eval_core.py` (Hydra entrypoint).

Key details:
```python
# src/eval/core.py
@torch.no_grad()
def forward_model(model, input_ids):
    outputs = model(input_ids)
    logits = outputs.logits if hasattr(outputs, "logits") else outputs
    ...

def evaluate_task(...):
    # sum+count reduction (lighter than full correct vector)
    correct_sum = torch.tensor(0.0, device=device)
    count = torch.tensor(0.0, device=device)
    for idx in range(rank, len(data), world_size):
        correct_sum += float(evaluate_example(...))
        count += 1.0
    if world_size > 1:
        dist.all_reduce(correct_sum, op=dist.ReduceOp.SUM)
        dist.all_reduce(count, op=dist.ReduceOp.SUM)
    return (correct_sum / count).item()
```

Training hook (nanochat-aligned):
- Add `core_metric_every` + `core_metric_max_per_task` to config (default `2000`/`500`).
- In `train.py`, call `evaluate_model(...)` on schedule (all ranks run, rank 0 logs).
- If model is compiled, use `orig_model` for CORE (variable-length inputs).
- Log a single scalar via `logger.log_metrics(step, {"metric": core_metric}, prefix="core/")`.

Standalone:
- `script/eval_core.py` uses the same `evaluate_model(...)`.

### 6) CORE eval config group
**Files:** `src/config.py`, `configs/eval/core.yaml`, `configs/config.yaml`

Add:
```python
@dataclass
class EvalConfig:
    core_bundle_url: str = "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"
    core_bundle_dir: str = "/data2/.cache/nanochat/eval_bundle"
    core_metric_every: int = 2000
    core_metric_max_per_task: int = 500

@dataclass
class Config:
    ...
    eval: EvalConfig = field(default_factory=EvalConfig)
```

Hydra defaults:
```yaml
defaults:
  - eval: core
```

## Validation steps (after approval)
1) `nvidia-smi` (required before eval).
2) Single GPU: `python train.py +experiment=debug` → eval loss stable.
3) Multi-GPU: `torchrun --nproc_per_node=2 train.py +experiment=debug` → eval loss matches single GPU.
4) CORE eval: `torchrun --nproc_per_node=2 python -m script.eval_core +experiment=debug eval.core_max_per_task=16`.

## Decisions locked in
- Eval loss stays **CE** (not bpb).
- Distributed metric reduction uses **mean for all metrics** (no per-metric map).
- Defaults aligned to nanochat: `eval_interval=250`, `eval_tokens=20*524288`.
- CORE eval runs **both**: scheduled during training + standalone script.
- CORE logging in wandb is **one scalar** under `core/metric` (no per-task metrics in wandb).

## Changes explicitly avoided
- No changes to `src/models/model_base.py` or routing logic.
- No edits in `nanochat_updated/` or other vendored repos.
