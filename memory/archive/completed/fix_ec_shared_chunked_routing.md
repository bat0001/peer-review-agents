# Plan: Fix EC_shared chunked routing + add CLI flag for per-device bsz

## Context & Findings

- `ec_shared` currently **does not use chunked routing** because `GECSharedMLP.forward()` bypasses `ECSharedMLP.forward_topk()` entirely (no override of `forward()`).
- `ECSharedMLP.forward_topk()` still references **removed RouterMixin helpers** (`self.apply_router_activation`, `self.compute_fanout`) and a **stale cutoff accumulator** (`engine.cutoff_accumulator`).
- `ec_shared` cannot use expert parallelism (EP) by config validation; training scripts already disable EP for non-GEC model types.

## Goals

1. Ensure `ec_shared` uses chunked top‑k routing during training when `routing_chunk_seqs` is set (including per‑sequence routing).
2. Make `ECSharedMLP.forward_topk()` compatible with the **new routing utilities** (`router_utils.apply_router_activation`, `compute_fanout`).
3. Add a CLI flag in `script/train.sh` to set **per‑device batch size** (the “bsz” you want), with a name you approve.

---

## Files to Edit (with snippets)

### 1) `src/models/ec_shared.py`

**Current (problematic) behavior** — no `forward()` override, RouterMixin helpers used:

```python
class ECSharedMLP(GECSharedMLP):
    def forward_topk(self, x, layer_idx=0):
        if self.routing_chunk_seqs is None:
            return super().forward(x, layer_idx)
        ...
        weights = self.apply_router_activation(values_flat, self.config.router_activation)
        fanout = self.compute_fanout(...)
        ...
        if self.engine.cutoff_accumulator is None:
            self.engine.cutoff_accumulator = []
        self.engine.cutoff_accumulator.append(avg_cutoffs)
```

**Planned changes (high‑level)**:

```python
from .router_utils import apply_router_activation, compute_fanout

class ECSharedMLP(GECSharedMLP):
    def forward(self, x, layer_idx=0):
        if (not self.training) or (self.routing_mode == "threshold"):
            return super().forward(x, layer_idx)
        return self.forward_topk(x, layer_idx)

    def forward_topk(self, x, layer_idx=0):
        ...
        router_logits = self.engine.router(x).float()
        router_logits_flat = router_logits.view(-1, n_routed_experts)
        all_weights, shared_weights = apply_router_activation(
            router_logits_flat, self.config.router_activation, self.config.granularity
        )
        # topk on raw logits (per‑chunk, per‑expert)
        topk_values, topk_indices = torch.topk(...)
        cutoffs = topk_values[:, :, -1]
        if self.training:
            avg_cutoffs = cutoffs.mean(dim=0)
            self.engine.cutoff_accum_sum.add_(avg_cutoffs)
            self.engine.cutoff_accum_count.add_(1)

        # gather selected weights from all_weights
        weights_flat = torch.gather(all_weights.t(), dim=1, index=indices_flat).reshape(...)
        fanout = compute_fanout(n_tokens, permutation_indices, x.device, torch.float32)

        # normalization_mode: fanout vs none (mirror gec_shared)
        if normalization_mode == "fanout":
            normalizer = fanout + 1.0
            weights_norm = weights_flat / normalizer[permutation_indices]
            shared_weights = 1.0 / normalizer
        else:
            weights_norm = weights_flat
            if shared_weights is None:
                shared_weights = torch.ones_like(fanout)

        # apply weights, scatter, add shared expert
        ...
```

**Notes**
- Use `self._shared_expert_forward(x_flat)` instead of duplicating the shared MLP math.
- Keep `compute_routing_metrics()` inputs consistent with GEC_shared:
  - `token_fanout` should include shared expert (`fanout + 1`).
  - Pass raw `fanout` as `normalizer` for metrics.

---

### 2) `script/train.sh`

**Current CLI** (no per‑device bsz flag, only env var `MICRO_BATCH_SIZE`):

```bash
--batch-size) TOTAL_BATCH_SIZE="$2"; shift 2;;
...
[[ -n "${MICRO_BATCH_SIZE:-}" ]] && args+=("training.per_device_batch_size=${MICRO_BATCH_SIZE}")
```

**Planned change (exact flag name TBD by you)**:

```bash
--chunk_size) PER_DEVICE_BSZ="$2"; shift 2;;   # or --bsz / --micro-batch-size
...
[[ -n "${PER_DEVICE_BSZ:-}" ]] && args+=("training.per_device_batch_size=${PER_DEVICE_BSZ}")
```

I’ll keep the existing `--batch-size` (total token batch size) and add **one new flag** for per‑device batch size.

---

## Step‑by‑Step Execution Plan

1) **Update `ec_shared` routing dispatch**
   - Add `forward()` override to route training → `forward_topk()` and eval/threshold → `super().forward()`.
   - This ensures `routing_chunk_seqs` actually activates chunked routing.

2) **Refactor `ECSharedMLP.forward_topk()`**
   - Replace RouterMixin helpers with `router_utils.apply_router_activation()` and `compute_fanout()`.
   - Compute `router_logits` in fp32 (match engine behavior).
   - Perform per‑chunk top‑k on **raw logits**.
   - Accumulate cutoff EMA using `engine.cutoff_accum_sum` + `engine.cutoff_accum_count`.
   - Gather weights from **all logits** (handles `softmax_k`/`softmax_e` correctly).
   - Apply `normalization_mode` exactly like `GECSharedMLP`.
   - Use shared expert forward via `_shared_expert_forward()`.
   - Keep metrics consistent (fanout+1, shared expert usage prepended).

3) **Add per‑device bsz flag to `script/train.sh`**
   - Implement the flag name you confirm (see below).
   - Map it to `training.per_device_batch_size`.
   - Leave `--batch-size` (total tokens) untouched.

4) **Optional sanity check (if you want me to run)**
   - `nvidia-smi` first (per repo rules).
   - Example:  
     `./script/train.sh --mlp ec_shared --g 2 --e 8 --chunk_size 1 --no-ep --experiment debug`  
     plus `training.max_steps=2` override.

---

## Open Choice (your call)

**Flag name for per‑device batch size**:
- If you want **`--chunk_size`** to mean *per‑device batch size*, I’ll do that.
- If you want **`--chunk_size`** to mean *routing chunk size* (`model.routing_chunk_seqs`), I’ll do that instead and add a separate `--bsz` for per‑device batch size.

Tell me which meaning you want for `--chunk_size` so I wire the CLI correctly.
