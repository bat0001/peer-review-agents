# Plan: Align nano_gec with nanochat_updated data/tokenizer/eval

## Context and goal
You want scaled-up experiments to match nanochat's setting (data, tokenizer, eval), while keeping GEC/MoE + Hydra + existing metrics. You also no longer care about kernel benchmarks, and you want to drop support for legacy `.npy` data pipelines. nanochat was updated and is present as `nanochat_updated/` (read-only per repo rules).

This plan focuses on integrating nanochat_updated features into this repo and includes concrete edit locations with snippets.

---

## Decision summary (recommended)
**Recommendation: integrate nanochat_updated features into the current repo** (this repo already has nanochat-style model/optimizer and Hydra; adding data/tokenizer/eval is incremental). This avoids an invasive fork and keeps MoE + Hydra intact.

**Why:**
- You already have MoE variants, Hydra configs, metrics, and GEC routing in place.
- Only missing pieces are data loader (parquet + tokenizer) and CORE evaluation.
- nanochat_updated is present as a reference but is read-only; editing it is disallowed here.

---

## Plan: import nanochat_updated features into this repo

### Phase 0: lock decisions and prerequisites
1) Standardize tokenizer naming on nanochat RustBPE only:
   - Use `tokenizer_type: rustbpe` and `tokenizer_dir` = `/data2/.cache/nanochat/tokenizer`.
   - Remove legacy `data.tokenizer` field and any tiktoken-only paths from configs.
2) Standardize cache + data roots under `/data2`:
   - HF cache: `HF_HOME=/data2/.cache/huggingface` (already in `~/.bashrc`); ensure non-interactive runs export it (optionally `HF_DATASETS_CACHE`/`HF_HUB_CACHE`).
   - nanochat artifacts: set `NANOCHAT_BASE_DIR=/data2/.cache/nanochat` for tokenizer/eval bundle/parquet downloads.
   - Repo defaults: set data roots under `/data2` and update any scripts that hardcode cache dirs.
   - Audit for `~/.cache` or `/workspace` and fix any remaining paths so downloads land in `/data2`.
3) ✅ **DONE** - Created new `nanochat` conda env with:
   - Python 3.12, CUDA 12.8 toolkit, PyTorch 2.9.1+cu128
   - Packages: rustbpe, tiktoken, pyarrow, wandb, requests, filelock, jinja2, numpy
   - Updated `requirements.txt` (removed datasets/matplotlib, added rustbpe/pyarrow/etc.)
   - Env path: `/data2/hanchi/miniconda3/envs/nanochat`
4) Drop legacy `.npy` data support:
   - Remove `.npy` loader logic and config fields (`use_sharded`, `shard_size`, legacy `data_path` expectations).
   - Delete `utils/fineweb.py` and `utils/fineweb_byte.py` (legacy `.npy` generators).
5) Add explicit nanochat-style model sizes via config files:
   - New `configs/model_size/dXX.yaml` files with `n_layer=depth`, `n_embd=depth*64`, and `n_head` selected for `head_dim≈128`.
   - Include all even depths from d4 to d34 (d4, d6, …, d34), covering smaller than d20 and the documented nanochat sizes.
6) Integrate CORE eval in training hook + standalone script (shared module).
7) Eval uses `model.eval()` only (no routing_mode override).

### Phase 1: data + tokenizer integration
**Goal:** support nanochat-style parquet streaming with tokenizer, replacing the legacy `.npy` shard pipeline.

Edits and additions:
- Add nanochat-compatible tokenizer wrapper (RustBPE only, load from directory).
- Add a parquet streaming dataloader similar to `nanochat_updated/nanochat/dataloader.py`.
- Update Hydra config to use nanochat tokenizer fields and parquet data roots (no format selector).
- Ensure val split uses the last parquet shard only (nanochat default).

Planned edits (snippets from current files):

`src/data_loader.py` (planned parquet-only loader):
```python

def create_data_loader(
    data_path: str,
    batch_size: int,
    seq_len: int,
    tokenizer_dir: str,
    split: str = "train",
) -> Iterator[Tuple[torch.Tensor, torch.Tensor]]:
    ...
```
Planned change: replace this loader with a parquet-only nanochat loader (no `format` switch).

`src/config.py` DataConfig (planned):
```python
@dataclass
class DataConfig:
    data_path: str = "/data2/.../parquet"
    tokenizer_type: str = "rustbpe"
    tokenizer_dir: str = "/data2/.cache/nanochat/tokenizer"
    tokenizer_threads: int = 8
    tokenizer_batch_size: int = 512
    nanochat_base_dir: str = "/data2/.cache/nanochat"
    num_workers: int = 4
```
Planned change: remove `.npy`-specific fields and add `tokenizer_type`, `tokenizer_dir`, `tokenizer_threads`, `tokenizer_batch_size`, and `nanochat_base_dir` (default `/data2/.cache/nanochat`).

`configs/config.yaml` data block (planned):
```yaml
data:
  data_path: "/data2/.../parquet"
  tokenizer_type: "rustbpe"
  tokenizer_dir: "/data2/.cache/nanochat/tokenizer"
  tokenizer_threads: 8
  tokenizer_batch_size: 512
  nanochat_base_dir: "/data2/.cache/nanochat"
  num_workers: 4
```
Planned change: replace with parquet/nanochat-oriented fields only (no `format` selector).

New files to add (copied/adapted from nanochat_updated, but placed under `src/`):
- `src/tokenizer.py` (RustBPETokenizer + get_token_bytes)
- `src/data/nanochat_dataset.py` (download/list parquet shards)
- `src/data/nanochat_dataloader.py` (tokenizing distributed data loader)

New model size configs to add (nanochat-style):
- `configs/model_size/d4.yaml` through `configs/model_size/d34.yaml` (even depths).

Dependencies to add:
- `pyarrow`, `tokenizers`, `rustbpe`, `filelock`, `jinja2`, `requests` (update `requirements.txt` + `setup.py`).

### Phase 2: CORE evaluation integration (train hook + script)
**Goal:** adopt nanochat CORE eval using our models, shared between training and a standalone script.

Edits/additions:
- Copy `nanochat_updated/nanochat/core_eval.py` to `src/eval/core.py` with ModelOutput adapter.
- Add `script/eval_core.py` Hydra entrypoint.
- Add a scheduled CORE eval hook in `train.py` (all ranks run; rank 0 logs a single scalar).
- Use `model.eval()` only (no routing_mode override); restore prior train/eval state after eval.

### Phase 2b: Val loss eval refactor (nanochat-aligned)
**Goal:** align val loss evaluation with nanochat_updated defaults and distributed behavior.

Edits/additions:
- Add `src/eval/val_loss.py` and `src/eval/__init__.py`.
- Add mean-reduction helpers in `src/utils/distributed.py` for scalar/list metrics.
- Update `train.py` to call `run_val_eval(...)` and compute eval steps from `eval_tokens`.
- Default to nanochat eval cadence (`eval_interval=250`, `eval_tokens=20*524288`).

### Phase 3: configs + logging
- Add `configs/eval/core.yaml` with: `core_metric_every`, `core_metric_max_per_task`, `core_bundle_url`, `core_bundle_dir`.
- Add `training.eval_interval=250` and `training.eval_tokens=20*524288` defaults in config + training YAMLs.
- Remove legacy data fields from all configs (`data.tokenizer`, `use_sharded`, `shard_size`).
- Ensure `config.model.vocab_size` is set from tokenizer when nanochat tokenizer is selected.
- Log eval results with `Logger.log_metrics(..., prefix="eval/")` so they appear in existing metric hierarchy.

### Phase 4: benchmarks de-emphasis (no deletes yet)
- Update docs (README + configs/README) to mark benchmarks optional/not used for this phase.
- Leave benchmark code intact for now (no destructive changes).

### Phase 5: tests + validation
- Add a dataloader smoke test for parquet loader (requires local parquet shard).
- Add a CORE eval smoke test with tiny subset (if eval bundle available).
- Run `test/test_weight_init.py` if we change any init or padding in model.

---

## Proposed order of implementation
1) Align cache/data roots under `/data2` and upgrade torch to 2.9 (env + config/script updates).
2) Remove legacy `.npy` data support (loader + config fields) and delete `utils/fineweb*.py`.
3) Add tokenizer + parquet dataloader modules (no model changes yet).
4) Add nanochat-style model size configs (`dXX`).
5) Wire data loader selection in `train.py` (parquet-only).
6) Add eval refactor (val_loss module + CORE eval, training hook + script, eval defaults).
7) Update docs + smoke tests.

---

## Decisions confirmed
- Tokenizer: RustBPE only (no tiktoken fallback)
- Tokenizer dir: `/data2/.cache/nanochat/tokenizer`
- Model sizes: all even depths from d4 to d34
- CORE eval via training hook + standalone script (no chat tasks)
- Eval uses `model.eval()` only (no routing_mode override)
- Eval defaults: `eval_interval=250`, `eval_tokens=20*524288`
- Local checkpoints only (no HF model support)
- Torch pin: `torch>=2.9.*`
