# Refactor Options: Drop Fanout Norm, Single Scatter Backend, Keep/Expand Metrics

Date: 2026-02-07

## Goals (Per Request)

- **No fanout normalization** going forward (remove `normalization_mode: fanout` usage; likely remove the config surface too).
- **Only one scatter implementation**: `index_add_fp32` (PyTorch `index_add_` with FP32 accumulation).
- **Keep all existing metrics** and make it easier to add more (especially eval-only metrics).
- **Save as many LOC as possible** via simplification and refactoring.
- **Do not edit code yet** (this doc is a proposal only).

## Constraints / Notes

- Metrics are currently designed to be computed as tensors inside the model/engine and converted to **Python scalars/lists** in `BaseGPT.forward()` to avoid distributed deadlocks.
- If we fully remove fanout normalization, then for `router_activation in {sigmoid,relu,softmax_k}`, output scale changes (tokens selected by many experts will sum rather than average). If we want stable scaling without fanout norm, we should strongly bias toward `router_activation=softmax_e*` or introduce a different normalization rule (see options).

## Current Code Map (Relevant Hotspots)

### Fanout normalization (the thing we want to stop using)

- `src/models/gec.py`
  - Applies `weights_flat / fanout[indices_flat]` when `normalization_mode == "fanout"`.
- `src/models/gec_shared.py`
  - Applies `weights_flat / (fanout+1)` and `shared_weights = 1/(fanout+1)` when `normalization_mode == "fanout"`.
- `src/models/ec_shared.py`
  - Duplicates the same normalization logic (but EC/EC_shared are currently in a partially legacy state).
- Validation surface:
  - `src/models/model_base.py:ModelConfig.normalization_mode`
  - `src/config.py` validates `normalization_mode` and enforces `softmax_e* => normalization_mode=none`.

### Scatter backend selection (we want to collapse to a single backend)

- `src/ops/scatter_backends.py`
  - Implements `IndexAddScatter`, `IndexAddScatterFP32`, `CSRScatter`, `CSRScatterOptimized`, and `get_scatter()`.
- CSR implementation is large and spans multiple files:
  - `src/ops/csr.py` (429 LOC)
  - `src/ops/csr_optimized.py` (202 LOC)
  - `src/kernels/csr.py` (551 LOC)
  - `src/kernels/csr_optimized.py` (198 LOC)
  - `src/kernels/__init__.py` exports CSR symbols
  - Total CSR-related LOC in `src/`: ~1,646 LOC (not counting benchmarks/tests).

### Metrics pipeline (we must preserve)

- Routing metrics are centralized:
  - `src/utils/routing_metrics.py:compute_routing_metrics()` (returns tensors)
  - Called by:
    - `src/models/engines/engine.py:ExpertEngine._compute_metrics()`
    - `src/models/engines/parallel_experts_manual.py:ParallelExperts._compute_metrics()`
- Conversion to Python types (critical invariant):
  - `src/models/model_base.py:BaseGPT._metrics_to_scalars()`
  - Training loop asserts no tensors in `train.py`.
- Logging:
  - `src/utils/logger.py` + `src/utils/metrics_organizer.py`
  - Eval metrics aggregation in `src/eval/val_loss.py`.

### Clearly-dead / unfinished code worth removing in any serious LOC-reduction

- `src/models/ec.py` imports `RouterMixin` (which no longer exists) and is effectively broken/unmaintained.
- `src/models/engines/scatter.py` is unfinished (`assert False`, incorrect `super()` usage).
- Naming footgun: `src/utils.py` (module file) exists alongside `src/utils/` (package).

## Refactor Options

### Option 0: “No Behavior Change”, Just Hard Defaults (lowest risk, minimal LOC saved)

Keep most code, but make the unused features “dead by config”:

- Force:
  - `model.scatter_backend = "index_add_fp32"` everywhere (configs, defaults)
  - `model.normalization_mode = "none"` everywhere (configs, defaults)
- Keep CSR + fanout branches in code (but never used).

Pros:
- Very low risk.
- No massive deletions, fewer test/benchmark ripples.

Cons:
- **Almost no LOC saved** (violates the “save as many LOC as possible” spirit).
- Leaves lots of complexity that will rot.

When to pick:
- You want to move fast on experiments now and only prune later.

---

### Option 1: “Surgical Delete”: remove fanout norm and scatter selection + delete CSR (big LOC win, still bounded)

Core idea:
- Remove runtime/config paths for features you won’t use:
  - `normalization_mode == "fanout"`
  - `scatter_backend` selection
  - CSR kernels and CSR scatter ops

Concrete steps (high-level):

1. **Scatter**
   - Replace `src/ops/scatter_backends.py` with a single `IndexAddScatterFP32` implementation.
   - Delete CSR code:
     - `src/ops/csr.py`
     - `src/ops/csr_optimized.py`
     - `src/kernels/csr.py`
     - `src/kernels/csr_optimized.py`
   - Update `src/kernels/__init__.py` to stop exporting CSR symbols.
   - Update `src/models/gec.py` and `src/models/gec_shared.py` to construct the single scatter backend (no factory).

2. **Fanout norm**
   - Delete `normalization_mode` from:
     - `src/models/model_base.py:ModelConfig`
     - `src/config.py` validation
     - `configs/mlp/*.yaml` comments/fields
   - Remove normalization branches from:
     - `src/models/gec.py`
     - `src/models/gec_shared.py`
     - `src/models/ec_shared.py` (if retained)
   - Keep computing `fanout` in the engine for metrics (do not remove `compute_fanout()` usage).

3. **Metrics**
   - No deletions. Ensure the same keys still flow.
   - If any metrics depend on “normalizer”, keep passing `fanout` to metrics (still computed).

Expected LOC savings (core `src/` only):
- CSR stack removal alone: ~1.6k LOC.
- Scatter backend simplification: `src/ops/scatter_backends.py` shrinks drastically.
- Small additional savings from removing `normalization_mode` plumbing and branches.

Main risks:
- If you still plan to use `router_activation=sigmoid/relu/softmax_k`, removing fanout normalization changes output scaling and may require retuning.
- Tests/benchmarks that reference CSR must be removed or rewritten.

---

### Option 2 (Recommended): Option 1 + “Unify Routing” (delete EC/EC_shared implementations; move chunking into ExpertEngine)

Core idea:
- Make `ExpertEngine.forward_topk()` support chunked routing via `routing_chunk_seqs`.
- Then `ECSharedMLP` becomes redundant; `ECMLP` can be deleted (and is currently broken anyway).

Concrete steps (high-level):

1. Do everything in **Option 1**.

2. **Move chunking into the engine**
   - Add chunked top-k support to:
     - `src/models/engines/engine.py:ExpertEngine.forward_topk()`
   - Input: `config.routing_chunk_seqs` (already exists in `ModelConfig`).
   - Output format stays identical:
     - `indices_batched`: `(n_routed_experts, k_total)` (with k_total = `n_chunks * k_per_chunk`)
     - `indices_flat`: flattened view
     - `weights_flat`: gathered from `all_weights` exactly like current global routing path.
   - Metric compatibility:
     - `compute_routing_metrics()` already accepts `cutoffs` as `(n_chunks, n_experts)` and averages internally, so no special-case needed.

3. **Delete dead / duplicated routing implementations**
   - Delete:
     - `src/models/ec.py` (broken legacy)
     - `src/models/ec_shared.py` (duplicate chunk routing)
     - `src/models/engines/scatter.py` (unfinished)
     - `src/utils.py` (file) to remove ambiguity with `src/utils/` package
   - Decide on config surface:
     - Either remove model types `ec`/`ec_shared` from validation entirely, or treat them as aliases of `gec`/`gec_shared` (with `routing_chunk_seqs != None`).

Expected LOC savings (core `src/` only):
- Option 1 savings +
- `ec.py` (~329) + `ec_shared.py` (~178) + `engines/scatter.py` (~63) + `src/utils.py` (~43)
- Net additional: ~600 LOC removed (even after adding some chunking code in `engine.py`).

Main risks:
- Requires careful correctness checks for chunking (index offsets, per-chunk `k` formula for shared vs non-shared).

Why this option matches your goals best:
- Removes a lot of dead/duplicate code while keeping metrics centralized.
- Future metric additions happen in **one place** (`src/utils/routing_metrics.py`) and apply to all routing modes.

---

### Option 3: “Narrow the Product”: keep only `gec_shared` (and maybe `dense`), delete everything else (maximum LOC reduction)

Core idea:
- If you know you will only train/eval one architecture, delete baselines/variants.

Possible deletions (depending on what you truly won’t use):
- Remove routed-only model:
  - `src/models/gec.py`
- Remove token-choice baselines:
  - `src/models/scattermoe_tc.py`
- Remove expert-parallelism path (EP) if you won’t run it:
  - `src/models/engines/parallel_experts_manual.py` (~587 LOC)
  - `src/ops/all_to_all.py` + `src/ops/prealloc_all_to_all.py` (~257 LOC)
  - EP-only tests and checkpoint code paths.
- Remove benchmark suites if they are no longer used for validation:
  - `benchmark/` is ~5.8k LOC of Python alone.
- Remove broken/outdated tests (many currently reference missing modules, e.g., `test/test_visualizations.py` imports `src.trainer` which does not exist).

Pros:
- Biggest LOC reduction, simplest maintenance.

Cons:
- Loses baselines + validation tooling unless replaced.
- Harder to compare against older results.

---

### Option 4: “Collapse Router Activations” (extra simplification, optional add-on)

If you truly won’t use fanout normalization and want fewer routing semantics:
- Restrict `router_activation` to a single family (likely `softmax_e` and/or `softmax_e_shared_out`).
- Then remove:
  - `sigmoid`, `relu`, `softmax_k` code paths in `src/models/router_utils.py`
  - proxy logic in `src/utils/routing_metrics.py` that approximates “all_norm_sum” for unsupported activations
  - validation branches in `src/models/model_base.py` / `src/config.py`

Pros:
- Simplifies routing semantics and reduces edge-case metrics code.

Cons:
- Removes experimentation knobs; requires commitment.

## Metrics: “Keep All” + Future Expansion Strategy

To keep metrics stable while enabling more eval-only metrics:

- Keep `src/utils/routing_metrics.py` as the **single source of truth** for routing metrics.
- Add an explicit “eval-only metrics” hook:
  - Either extend `compute_routing_metrics(..., is_training: bool, ...)`, or
  - Add a second function like `compute_eval_routing_metrics(...)` called only under `torch.no_grad()` / `not model.training`.
- Standardize `layer_data` emission:
  - Today, only EC/EC_shared attach `metrics["layer_data"]` for visualization.
  - If you care about eval visualizations for GEC/GEC_shared, emit `layer_data` from the engine (for representative layers only) so it’s consistent and centralized.

## Decision Questions (Need Your Answers Before Implementation)

1. Remove `normalization_mode` entirely (always “none”), or keep it as a deprecated field that is ignored?
2. When you say “only index_add_fp32 scatter”, is that only for the **model aggregation path** (`src/ops/scatter_backends.py`), or do you also want to delete Triton gather/scatter kernels under `src/kernels/` and the `benchmark/permutation` tooling?
3. Do you want to keep `model_type=ec/ec_shared` as aliases, or delete those model types and rely solely on `routing_chunk_seqs` with `gec/gec_shared`?

