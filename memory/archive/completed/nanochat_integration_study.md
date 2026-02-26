# Nanochat Integration Study – Stage 1

**Status**: ✅ ARCHIVED - Completed (October 19, 2025)
**Superseded by**: memory/archive/completed/nanochat_integration_final_plan.md
**Note**: This was the initial study phase. See IMPLEMENTATION.md for final integration.

---

**Original Study:**

Scope: compare the in-repo (`src/`, `configs/`, `train.py`) training stack to `nanochat/nanochat/` with emphasis on optimizers, parameter-wise learning rates, initialization, LR scheduling, model architecture, and trainer setup. Also record paper/code references cited inside Nanochat.

## 1. Optimizers
- **Nanochat (`nanochat/gpt.py`, `nanochat/adamw.py`, `nanochat/muon.py`)**
  - Splits parameters into two families: embeddings + LM head (`AdamW`) versus all transformer matrices (`Muon`).
  - `DistAdamW` shards states/gradients ZeRO-2 style and supports per-parameter `lr_mul` & `wd_mul`.
  - `Muon` (and `DistMuon`) orthogonalizes linear-layer updates via Newton–Schulz; momentum buffers and aspect-ratio scaling baked in.
  - Defaults: AdamW β=(0.8, 0.95), ε=1e-10, no weight decay; Muon momentum initialised at 0.95.
- **Current project (`src/optimizer.py`)**
  - Single fused `AdamW` optimizer over all parameters with two groups (decay vs no-decay). `betas=(0.9,0.95)`, ε=1e-8.
  - No custom handling for distributed optimizer state beyond standard DDP gradients.
- **Takeaways**
  - Nanochat relies on Muon for linear weights—an orthogonal update rule not present here.
  - State sharding and distributed-aware optimizers are assumed in Nanochat but absent in current trainer.

## 2. Parameter-Wise Learning Rates
- **Nanochat**
  - `setup_optimizers` assigns distinct base LRs: matrix (`0.02`), embedding (`0.2`), unembedding (`0.004`) and scales them ∝ `1/√d_model`.
  - Supports per-group LR ramping via `get_lr_multiplier`, and momentum annealing for Muon (`get_muon_momentum`).
- **Current project**
  - Single scalar LR from config propagated to all optimizer groups.
  - Only differentiation is weight-decay on/off; no LR multipliers or per-layer schedules.
- **Takeaways**
  - Migrating Nanochat’s design would require richer param-group metadata (embeddings vs matrices vs router weights) and LR scaling hooks.

## 3. Initialization
- **Nanochat (`nanochat/gpt.py`)**
  - Meta-device construction (`model.to_empty`) + custom init: `std = 1/√fan_in * min(1, √(fan_out/fan_in))` (comment cites arXiv:2310.17813).
  - Zeroes LM head and every `c_proj` weight to start residual branches inactive.
  - Token embedding cast to bfloat16 immediately; rotary caches precomputed.
  - Activation stack: RMSNorm without parameters, ReLU² MLP, QK normalization, logits soft-cap.
- **Current project**
  - Standard GPT-2 style init: `Normal(0, 0.02)` plus residual scaling for `c_proj`. Learned LayerNorm γ/β, GELU MLP.
  - Positional embeddings learned (`wpe`), weight tying of `wte` and `lm_head`.
- **Takeaways**
  - Nanochat embraces more recent stability tricks (zero residual starts, QK norm, rotary-only positions). Aligning would mean rethinking init + block internals, especially if we keep GEC modules.

## 4. Learning Rate Schedule
- **Nanochat**
  - Manual scheduler per step: optional warmup (`warmup_ratio`), flat mid-phase, linear warmdown over last 20% of steps to `final_lr_frac`.
  - Separate Muon momentum schedule ramping 0.85→0.95 over first 300 steps.
  - No built-in cosine/Poly; logic embedded directly inside training scripts (`base_train.py`, etc.).
- **Current project**
  - Configurable cosine decay (`src/optimizer.get_lr_scheduler`) with warmup steps and floor LR.
  - Momentum is fixed (from optimizer betas); no secondary schedules.
- **Takeaways**
  - To mirror Nanochat we need custom scheduler hooks in trainer + ability to drive optimizer-specific hyperparameters (e.g., Muon momentum) each step.

## 5. Model Architecture
- **Nanochat GPT (`nanochat/gpt.py`)**
  - Rotary position embeddings (no learned `wpe`), RMSNorm everywhere with no affine params.
  - QK norm (RMS) before attention; Multi-Query Attention (`n_kv_head ≤ n_head`).
  - MLP uses bias-free linear layers and ReLU². Untied `wte`/`lm_head`; logits softcapped.
  - Optional KV cache management baked into model, inference-oriented utilities (`Engine`, `KVCache`).
- **Current BaseGPT (`src/models/model_base.py`)**
  - Learned token + position embeddings; `LayerNorm` with affine params.
  - Standard multi-head attention with `torch.nn.functional.scaled_dot_product_attention`.
  - GELU-based MLP (or GEC variants with expert choice). Weight tying between input/output embeddings.
- **Takeaways**
  - Nanochat prioritizes inference efficiency (MQA, RMSNorm) and training stability (QK norm, softcap). Integrating with GEC will need compatibility checks (e.g. router assumptions with ReLU² activations).

## 6. Trainer Setup
- **Nanochat (`scripts/base_train.py`, `nanochat/common.py`, `nanochat/dataloader.py`)**
  - Script-driven training: compute init handles CUDA+DDP, seeds, TF32 enablement. ASCII logging for visibility.
  - Token streaming from parquet shards with on-the-fly tokenization into pinned host buffers, feeding CUDA tensors asynchronously.
  - Gradient accumulation derived from total batch size and world tokens; manual timing + MFU reporting.
  - Two optimizers stepped sequentially; LR/momentum schedules applied explicitly before `opt.step()`.
  - Frequent evaluation hooks: validation bpb, CORE metric (DCLM tasks), sampling; saving via `checkpoint_manager`.
  - Uses `torch.compile` (static shapes) and meta device initialization to reduce peak allocation.
- **Current Trainer (`src/trainer.py`)**
  - Class-based Hydra-integrated loop with resumable checkpoints, unified metrics/logging, optional `torch.compile`.
  - Data loader abstraction chooses between pre-sharded `.npy` buffers and lazy tokenization.
  - Single optimizer & scheduler applied via helper functions; mixed precision via `torch.autocast`/`GradScaler`.
  - Evaluation uses configurable batch count but no built-in downstream metrics or sampling yet.
- **Takeaways**
  - Adopting Nanochat flow implies: script-to-class reconciliation, sharper data streaming (pinning, asynchronous host queues), multiple optimizers, and richer eval callbacks.

## Referenced Papers & External Code
- Muon optimizer blog by Keller Jordan (`nanochat/muon.py`): https://kellerjordan.github.io/posts/muon/
- CORE metric from DCLM paper (`nanochat/core_eval.py`): https://arxiv.org/abs/2406.11794
- Initialization comment references arXiv:2310.17813 (weight scaling heuristic for transformers).
- FLOP estimator cites Chinchilla-style formula (`arXiv:2204.02311`).
- DistAdamW attribution to modded-nanogpt (Keller, @vagrawal, etc.).

## Integration Notes (Next Steps Placeholder)
1. Prototype Muon/AdamW dual-optimizer support inside `src/trainer.Trainer` (requires optimizer registry + per-parameter tagging).
2. Audit GEC modules for compatibility with RMSNorm + ReLU²; determine if router metrics/normalization assumptions still hold.
3. Design scheduler interface that can drive both LR and optimizer-specific hyperparameters (e.g., Muon momentum).
4. Plan migration path for data streaming (parquet pipeline versus existing numpy shards) and evaluation tooling parity (CORE metric, sampling).
