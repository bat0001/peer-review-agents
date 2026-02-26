# Missing Parts: nanochat_updated_alignment_plan.md (filled after nanochat_updated study)

## Purpose
Capture concrete, file-level details needed to execute the alignment refactor.
This version resolves missing items using nanochat_updated as ground truth, plus repo study.

## Resolved details (from nanochat_updated + repo study)

### 1) File-by-file edit map (concrete)
- `src/data_loader.py`
  - Replace with parquet-only loader that delegates to `src/data/nanochat_dataloader.py`.
  - New signature: `create_data_loader(data_path, batch_size, seq_len, tokenizer_dir, tokenizer_threads, tokenizer_batch_size, split, device)`.
  - No `.npy` shards, no tiktoken, no resume state.

- `src/data/nanochat_dataset.py` (new)
  - Port from `nanochat_updated/nanochat/dataset.py`.
  - Constants:
    - `BASE_URL = "https://huggingface.co/datasets/karpathy/fineweb-edu-100b-shuffle/resolve/main"`
    - `MAX_SHARD = 1822`
    - `index_to_filename = lambda idx: f"shard_{idx:05d}.parquet"`
  - Functions:
    - `list_parquet_files(data_dir)` → sorted `.parquet` files, exclude `.tmp`.
    - `parquets_iter_batched(split, start, step, data_dir)` → yield row group text lists.
    - `download_single_file(index, data_dir)` → optional on-demand download with retries.
  - `data_dir` comes from config `data.data_path` (default `/data2/.cache/nanochat/base_data`).

- `src/data/nanochat_dataloader.py` (new)
  - Port from `nanochat_updated/nanochat/dataloader.py`, but **no resume support**.
  - Uses `get_dist_info()` from `src/utils/distributed.py`.
  - `parquet_paths = list_parquet_files(data_dir)`.
  - Train/val split: `[:-1]` for train, `[-1:]` for val (last shard only).
  - Row group iteration: `rg_idx = ddp_rank`, step = `ddp_world_size`.
  - Tokenization: `tokenizer.encode(batch, prepend=bos_id, num_threads=tokenizer_threads)`.
  - Chunk size: `tokenizer_batch_size` (default 128 to match nanochat).
  - Buffer: `deque` with `needed_tokens = B * T + 1`.
  - Device transfer: pin memory if CUDA, `non_blocking=True`.
  - Yields `(inputs, targets)` only; no state dict.

- `src/tokenizer.py`
  - Port RustBPE-only `RustBPETokenizer` from `nanochat_updated/nanochat/tokenizer.py`.
  - Required methods: `from_directory`, `encode`, `decode`, `get_bos_token_id`, `get_vocab_size`, `__call__`.
  - `encode` supports list-of-strings with `num_threads`, and `prepend` for BOS.
  - Load from `tokenizer.pkl` in `tokenizer_dir`.
  - Provide helper `get_tokenizer(tokenizer_dir)` to centralize loading.
  - No HF tokenizer/tiktoken inference path (no backward compatibility).

- `src/utils/download.py` (new)
  - Port `download_file_with_lock` + base dir helper from `nanochat_updated/nanochat/common.py`.
  - Use `filelock.FileLock` + `urllib.request`.
  - Base dir uses config `data.nanochat_base_dir` (default `/data2/.cache/nanochat`).

- `src/eval/val_loss.py` + `src/eval/__init__.py` (new)
  - From v3: `compute_eval_steps(...)`, `run_val_eval(...)` with shared evaluation.
  - Uses `eval_tokens` and `eval_interval` defaults aligned to nanochat.
  - Restores prior `model.training` state after eval.

- `src/eval/core.py` (new)
  - Port `nanochat_updated/nanochat/core_eval.py`.
  - `forward_model` adapter: `outputs.logits` if ModelOutput, else raw tensor.
  - `evaluate_task` uses **sum+count** reduction (avoid full correct vector).
  - Sequence cap uses `model.max_seq_len` if present, else `model.config.block_size`.
  - Tokenizer usage: `tokenizer(prompts, prepend=tokenizer.get_bos_token_id())`.

- `script/eval_core.py` (new)
  - Hydra entrypoint.
  - Uses `compute_init` + `print0`.
  - Loads model + tokenizer from local checkpoint only.
  - Runs `evaluate_model(..., max_per_task=cfg.eval.core_metric_max_per_task)`.
  - Rank 0 prints results.

- `train.py`
  - Replace inline `evaluate()` with `run_val_eval(...)` (val loss).
  - Use `build_val_loader = lambda: create_data_loader(..., split="val")` (fresh loader each eval).
  - Add CORE eval hook: all ranks run, rank 0 logs `core/metric`.
  - Use `orig_model` if compiled for CORE (variable-length inputs).
  - No resume logic added.

- `src/config.py`
  - `DataConfig` replaces legacy fields:
    - `data_path: "/data2/.cache/nanochat/base_data"`
    - `tokenizer_type: "rustbpe"`
    - `tokenizer_dir: "/data2/.cache/nanochat/tokenizer"`
    - `tokenizer_threads: 4`
    - `tokenizer_batch_size: 128`
    - `nanochat_base_dir: "/data2/.cache/nanochat"`
    - `num_workers: 4`
  - `TrainingConfig` adds:
    - `eval_interval: 250`
    - `eval_tokens: 20 * 524288`
  - New `EvalConfig`:
    - `core_metric_every: 2000`
    - `core_metric_max_per_task: 500`
    - `core_bundle_url: "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"`
    - `core_bundle_dir: "/data2/.cache/nanochat/eval_bundle"`
  - Update `Config` to include `eval: EvalConfig`.
  - Update `validate()` to check `data_path` exists (no `use_sharded`).

- `configs/*`
  - `configs/config.yaml`: new `data` block with `tokenizer_dir`, `tokenizer_threads`, `tokenizer_batch_size`, `nanochat_base_dir`; remove `use_sharded`/`shard_size`; set `data_path` to `/data2/.cache/nanochat/base_data`.
  - Defaults: add `- eval: core`.
  - `configs/training/*.yaml`: set `eval_interval=250`, add `eval_tokens=10485760`.
  - `configs/presets/*.yaml` + `configs/experiment/*.yaml`: remove legacy data fields, adopt new data keys.
  - Add `configs/eval/core.yaml`.
  - Add nanochat-style model size configs `configs/model_size/d4.yaml` through `d34.yaml`.

### 2) Call-site inventory for legacy data fields (rg results)
- `train.py`: `tokenizer_name=config.data.tokenizer` → replace with tokenizer_dir + threads + batch size.
- `src/config.py`: `DataConfig` has `tokenizer`, `use_sharded`, `shard_size`; `validate()` checks `use_sharded`.
- `configs/config.yaml`: `data.tokenizer`, `use_sharded`, `shard_size`.
- `configs/presets/dense_medium.yaml`, `configs/presets/gec_shared_tiny.yaml`: legacy data fields.
- `test/test_visualizations.py`: uses `data.use_sharded`.

### 3) Parquet loader parity (exact behavior)
- Train/val split: last shard is validation (`parquet_paths[-1:]`).
- Row group stride: `rg_idx = ddp_rank`, step = `ddp_world_size`.
- Tokenization: `tokenizer.encode(batch, prepend=bos_id, num_threads=tokenizer_threads)`.
- Batch chunking: `tokenizer_batch_size` per tokenization call (default 128).
- Token buffer: `deque` with `needed_tokens = B*T+1`.
- Device: pin memory if CUDA; `inputs/targets` moved with `non_blocking=True`.
- No resume state (`resume_state_dict` removed).

### 4) Tokenizer integration specifics
- Use `RustBPETokenizer.from_directory(tokenizer_dir)` (expects `tokenizer.pkl`).
- BOS token id via `<|bos|>`; prepended to each document.
- `encode` supports list input; returns list of token id lists.
- `config.model.vocab_size` should be set from tokenizer at load time (override config).
- No HF tokenizer path.

### 5) Eval refactor details (val loss + CORE)
- Val loss:
  - `eval_steps = eval_tokens // (per_device_batch_size * sequence_length * world_size)`.
  - Use `reduce_mean_scalar` / `reduce_mean_list` in `src/utils/distributed.py`.
  - `model.eval()` during eval, restore prior mode.
  - Log with `logger.log_metrics(..., prefix="eval/")`.
- CORE:
  - Use bundle from `core_bundle_url` + `core_bundle_dir`.
  - `evaluate_task` uses rank-strided indexing + sum/count reduction.
  - Log only `core/metric` (single scalar).

### 6) Dependencies + env (✅ COMPLETED)
- Created new `nanochat` conda env (not updating gec):
  - Path: `/data2/hanchi/miniconda3/envs/nanochat`
  - Python 3.12, CUDA 12.8 toolkit
  - PyTorch 2.9.1+cu128, triton 3.5.1
  - rustbpe, tiktoken, pyarrow, wandb, requests, filelock, jinja2, numpy
- `requirements.txt` updated:
  - torch>=2.9.0, numpy, triton
  - rustbpe, tiktoken, pyarrow, requests, filelock
  - hydra-core>=1.3.2, omegaconf>=2.3.0, PyYAML, tqdm
  - wandb, jinja2
  - Removed: datasets, matplotlib

### 7) Tests + validation
- Update `test/test_visualizations.py` data config to new fields (remove `use_sharded`).
- Add parquet loader smoke test (optional; requires local shard).
- Add CORE eval smoke test gated on eval bundle presence.
- Run `test/test_weight_init.py` only if init changes (not expected here).

### 8) Docs updates
- `README.md`: remove `fineweb.py` references; document parquet base_data + tokenizer paths.
- `configs/README.md`: update data field descriptions + eval defaults.

### 9) Risk / rollback notes
- Removing `.npy` support is a breaking change; rollback via git if needed.
- If eval bundle download is blocked, manually place `eval_bundle` under `core_bundle_dir`.

## Remaining open choices
- None. All items above are specified based on nanochat_updated + repo study.
