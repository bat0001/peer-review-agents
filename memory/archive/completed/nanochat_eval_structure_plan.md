# Plan: CORE eval integration (nanochat_updated, train hook + script)

## Goals
- Integrate **nanochat_updated CORE evaluation** into this repo for both training hook and standalone script.
- Keep CORE eval logic isolated in `src/eval/core.py` and reuse it in `train.py` and `script/eval_core.py`.
- Reuse as much of nanochat_updated as possible via minimal vendoring + adapters.
- Use Hydra entrypoints (scripts under `script/`), logging only one CORE scalar.

Non-goals (explicitly removed per request):
- Chat eval tasks (ARC/MMLU/GSM8K/HumanEval/SpellingBee)
- KV-cache inference engine
- Tokenizer eval tables
- BPB loss eval (unless you later ask for it)

---

## What nanochat_updated CORE eval does (study notes)

### Files
- `nanochat_updated/scripts/base_eval.py`
- `nanochat_updated/nanochat/core_eval.py`

### Flow
1. **Download eval bundle** (`eval_bundle.zip`) if missing.
2. Parse `core.yaml` for task metadata.
3. For each task:
   - Load JSONL data from `eval_data/`.
   - Shuffle deterministically, optionally crop `max_per_task`.
   - Evaluate with `core_eval.evaluate_task(...)`.
4. Compute **centered accuracy** using random baselines from `eval_meta_data.csv`.
5. Average centered results for CORE score.

### Scoring mechanics (no generation)
CORE eval does **not** require generation or sampling. It is **teacher-forced scoring** based on log-probabilities (and in one case exact-token matches). You can think of it as "prefill only" evaluation:

- We always **feed the full prompt** (including the candidate option or continuation) into the model and compute logits for every position.
- We then compute the **cross-entropy loss** for the continuation span only.Lower loss means higher probability.
- For language_modeling tasks, the metric is **exact-match** of argmax predictions across the continuation tokens (stricter than loss).

Concretely, `core_eval.forward_model(...)` does:
```python
outputs = model(input_ids)
logits = outputs.logits  # (B, T, V)
targets = input_ids rolled by one position
losses = cross_entropy(logits, targets)  # per-token loss
```
The last column is ignored since there is no next-token target.

#### Task-type specifics

1) **multiple_choice** (MC)
- Build one prompt per answer choice by appending the choice to the common prefix.
- Find the shared prefix length across options.
- For each option, take the **mean loss** over the choice tokens only.
- Pick the option with **lowest mean loss** (highest log-prob).

Pseudo:
```python
tokens = tokenizer(prompts, prepend=bos)
start = common_prefix_length(tokens)
end = len(tokens[i])
mean_loss_i = losses[i, start-1:end-1].mean()
pred = argmin(mean_loss_i)
```

2) **schema**
- Context varies, continuation is the same (shared suffix).
- Find the shared suffix length, and score only that suffix.
- Pick the context with lowest mean loss over the continuation.

3) **language_modeling** (LM)
- Two prompts: without continuation (prefix), with continuation (full).
- Score is **exact match**: argmax predictions must equal every continuation token.
- This is stricter than loss/perplexity and yields a 0/1 correctness.

Pseudo:
```python
prompt_without, prompt_with = render_lm(...)
tokens_with = tokenizer(prompt_with, prepend=bos)
start = len(tokens_without)
end = len(tokens_with)
pred_tokens = argmax(logits)[start-1:end-1]
is_correct = all(pred_tokens == tokens_with[start:end])
```

### Why no generation?
CORE is designed to be a **likelihood-based evaluation** (not sampling-based).
This makes it:
- Deterministic and cheaper than generation-heavy evals.
- Comparable across models via the same scoring mechanics.
- Aligned with the DCLM CORE protocol (centered accuracy).

### Task types supported
- `multiple_choice`: compare mean loss across options (lowest wins).
- `schema`: compare mean loss across contexts with fixed continuation.
- `language_modeling`: exact token match across continuation span.

### Key assumptions in core_eval
- Tokenizer supports `tokenizer(prompts, prepend=bos_token_id)` and `get_bos_token_id()`.
- Model forward returns logits compatible with cross-entropy.
- Optional `model.max_seq_len` for truncation (GPT-2 case).

### Distributed evaluation support
The nanochat implementation supports multi-GPU evaluation via `torch.distributed`:
- Examples are strided across ranks: `for idx in range(rank, len(data), world_size)`
- Results are synchronized via `dist.all_reduce()`
- Works with `torchrun` out of the box

For GEC with EP (expert parallel), all ranks must run eval since model forward uses all-to-all communication. Follow existing `train.py` pattern.

---

## Recommendation: reuse strategy

### Recommended (Option B): Vendor minimal CORE modules + adapters
Copy only the CORE eval logic into `src/` and adapt to our APIs.
- Avoids `PYTHONPATH` hacks.
- Keeps eval stable and easy to maintain.
- Minimal duplication (~1–2 files + download helper).

### Avoid
- Direct imports from `nanochat_updated/` (fragile path dependencies).
- Full rewrites (risk of drift from official metric).

---

## Proposed folder structure (CORE eval + shared eval package)

```
.
├── eval.py                      # Optional root wrapper (thin CLI delegator)
├── script/
│   └── eval_core.py             # Hydra entrypoint for CORE
├── src/
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── core.py               # Ported from nanochat_updated/nanochat/core_eval.py
│   │   └── val_loss.py           # From v3 (shared eval package)
│   └── utils/
│       └── download.py           # download_file_with_lock + bundle placement
```

Notes:
- If you want `eval.py` at root, it will just dispatch to `python -m script.eval_core`.
- No `tasks/` or `engine/` directories needed.

---

## Detailed change plan (file-by-file, with snippets)

### 1) `src/eval/core.py`
Port `nanochat_updated/nanochat/core_eval.py` with **one adapter**:
- Our model returns `ModelOutput`, not raw logits.

Complete adapter for `forward_model`:
```python
@torch.no_grad()
def forward_model(model, input_ids):
    """
    Take BxT tensor of token ids, return BxT tensor of losses and argmax predictions.
    The last column of losses is set to nan because we don't have autoregressive targets there.
    """
    batch_size, seq_len = input_ids.size()
    outputs = model(input_ids)
    # Handle both raw logits and ModelOutput
    logits = outputs.logits if hasattr(outputs, "logits") else outputs
    # Roll the tensor to the left by one position to get the (autoregressive) target ids
    target_ids = torch.roll(input_ids, shifts=-1, dims=1)
    # Calculate cross entropy at all positions
    losses = torch.nn.functional.cross_entropy(
        logits.view(batch_size * seq_len, -1),
        target_ids.view(batch_size * seq_len),
        reduction='none'
    ).view(batch_size, seq_len)
    # Set the last column to be nan because there is no autoregressive loss there
    losses[:, -1] = float('nan')
    # Get the argmax predictions at each position
    predictions = logits.argmax(dim=-1)
    return losses, predictions
```

Everything else stays identical to preserve CORE comparability.

---

### 2) `src/utils/download.py`
Add a small download helper (ported from nanochat_updated `common.py`), e.g.:
- `download_file_with_lock(url, filename, postprocess_fn=None)`
- `get_eval_bundle_dir()` (uses `NANOCHAT_BASE_DIR` or config path)

Snippet (conceptual):
```python
def get_eval_bundle_dir(base_dir: str) -> Path:
    return Path(base_dir) / "eval_bundle"
```

This avoids scattering ad-hoc download logic in the eval script.

---

### 3) `script/eval_core.py`
Hydra entrypoint for CORE eval. Responsible for:
- Loading model + tokenizer (local checkpoint only, no HF support).
- Downloading eval bundle if needed.
- Running `evaluate_model()` and printing CSV-like output.
- Following `train.py` distributed pattern (EP: all ranks run, only rank 0 logs).

Example skeleton:
```python
@hydra.main(config_path="../configs", config_name="config")
def main(cfg: Config):
    # Follow train.py pattern for distributed init
    ddp, rank, local_rank, world_size, device = compute_init(cfg)
    master_process = (rank == 0)

    model, tokenizer = load_model_for_eval(cfg, device)

    # EP: all ranks run eval (model forward needs all-to-all)
    results = evaluate_model(model, tokenizer, device, max_per_task=cfg.eval.core_metric_max_per_task)

    # Only rank 0 prints results
    if master_process:
        print_results(results)
```

We will reuse `compute_init()` and `print0()` from `src/utils/distributed.py`.

---

### 4) Training hook (train.py)
Add a scheduled CORE eval hook in `train.py` that calls the same `evaluate_model(...)`.
- Schedule via `eval.core_metric_every`.
- Use `eval.core_metric_max_per_task` during training.
- All ranks run, rank 0 logs a single scalar under `core/metric`.
- If the model is compiled, use the uncompiled `orig_model` for CORE (variable-length inputs).

Sketch:
```python
if step % cfg.eval.core_metric_every == 0 and step > 0:
    core_out = evaluate_model(
        model=orig_model if orig_model is not None else model,
        tokenizer=tokenizer,
        device=device,
        max_per_task=cfg.eval.core_metric_max_per_task,
    )
    if master_process:
        logger.log_metrics(step, {"metric": core_out["core_metric"]}, prefix="core/")
```

---

### 5) `src/config.py` + `configs/eval/core.yaml`
Add a small eval config group for CORE. Suggested fields:

```python
@dataclass
class EvalConfig:
    core_metric_every: int = 2000
    core_metric_max_per_task: int = 500
    core_bundle_url: str = "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"
    core_bundle_dir: str = "/data2/.cache/nanochat/eval_bundle"
```

`configs/config.yaml` defaults add:
```yaml
defaults:
  - eval: core
```

This keeps eval settings explicit without cluttering training configs.

---

### 6) Tokenizer compatibility
CORE eval needs:
- `get_bos_token_id()`
- `encode` for prompts

**Decision: RustBPE only** (no tiktoken adapter). The RustBPETokenizer from nanochat_updated provides both methods natively.

---

## Dependencies
Add to `requirements.txt` if missing:
- `jinja2` (templating for prompts)
- `filelock` + `requests` (download helper)
- `rustbpe` (tokenizer)

---

## Validation plan
1) `nvidia-smi` (required before eval)
2) `python -m script.eval_core +experiment=debug eval.core_metric_max_per_task=16`
3) `python train.py +experiment=debug` and confirm `core/metric` logs.
4) `torchrun --nproc_per_node=2 python -m script.eval_core +experiment=debug eval.core_metric_max_per_task=16`

---

## Decisions - RESOLVED
1) ✓ **Training hook + script** (shared `evaluate_model(...)`)
2) ✓ **`/data2/.cache/nanochat`** (matches alignment_plan)
3) ✓ **Local checkpoints only** (no `--hf-path`, no `transformers` dependency)
4) ✓ **RustBPE only** (no tiktoken fallback)
5) ✓ **Log a single CORE scalar** (`core/metric`)

---

## Implementation ready
All decisions confirmed. Proceed with code edits in the order above.
