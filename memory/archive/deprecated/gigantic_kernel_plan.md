# Megaplan: CSR Metadata Sharing & Fused Scatter/Gather Backward

> _Working document capturing design decisions, math derivations, and implementation roadmap for consolidating CSR metadata, plus formalizing fused kernels for gather/scatter backward passes with routing weights._

## 1. Motivation

### 1.1 Duplicate CSR Builds

- `CSRGatherOp.forward` and `CSRScatterOp.forward` both call `build_slot_indices`, resulting in two full passes over $E \cdot C$ slots per forward invocation.
- Benchmarks (`benchmark/permutation/scatter/*.py`, `test/test_csr_vs_index_add.py`) replicate the same flatten → argsort → bincount logic manually, causing maintenance drift.
- Goal: Build metadata once per expert forward, pass it into every consumer (gather/scatter forward/backward, metrics, debug).

### 1.2 Backward Weight Gradients

- Scatter with weights requires dot products between token gradients and expert activations per slot.
- Gather with weights (or gather feeding a weighted scatter) similarly needs per-slot scaling.
- We already have `_fused_gather_wgrad`, but its usage is implicit; we want a clear derivation + extension plan (e.g., CSR backend or sequential-add variants).

## 2. Notation

| Symbol | Meaning |
| --- | --- |
| $N$ | $\text{num\_tokens} = B \times T$ |
| $E$ | $\text{n\_experts}$ (routed) |
| $C$ | $\text{capacity} = N / \text{expansion}$ (expert slots) |
| $H$ | hidden dimension |
| $\ell = e \cdot C + s$ | linear slot id |
| $t_\ell$ | token id stored at slot $\ell$ ($indices[\ell]$) |
| $w_\ell$ | router weight per slot (after normalization) |
| $a_\ell$ | expert output vector (BF16) |
| $g_t$ | upstream gradient for token $t$ |

## 3. CSR Metadata Sharing

### 3.1 Desired API

```python
@dataclass
class CSRMetadata:
    slot_indices: torch.Tensor   # (E*C',) valid slot linear ids
    slot_offsets: torch.Tensor   # (N,)
    slot_counts: torch.Tensor    # (N,)
    max_experts: int
    num_tokens: int

def build_csr_metadata(indices, num_tokens, max_experts) -> CSRMetadata:
    ...
```

- `slot_indices` already equals `build_slot_indices(...)[0]`; we simply package the triple with config.
- `max_experts` recorded to keep kernel launch consistent.
- Should support caching (store on ctx, pass to sequential kernels, metrics).

### 3.2 Consumers

1. **CSRGatherOp**  
   - Forward uses simple gather.  
   - Backward calls `_csr_scatter_sum`; provide `CSRMetadata` to skip recomputation.
2. **CSRScatterOp**  
   - Forward uses `_csr_scatter_sum`; can accept metadata directly.  
   - Backward (gather) needs the same metadata; store reference on ctx.
3. **ExpertEngineCSR**  
   - Build metadata immediately after `topk_indices`.  
   - Pass to `csr_gather` (for caching) and `csr_scatter_sum`.  
   - Save for metrics (fanout histograms) and diagnostics.
4. **Benchmarks**  
   - Replace ad-hoc `build_inverse_indices` with `build_csr_metadata`.  
   - Expose metadata build timing separately.

### 3.3 Migration Steps

1. Introduce `CSRMetadata` + builder in `src/ops/csr.py`.
2. Add optional `meta` argument to `csr_gather` / `csr_scatter_sum`.  
   - If `meta is None`: build internally (backward-compatible).  
   - If provided: assert shapes, bypass build.  
3. Update ops to store metadata on ctx for backward path.  
   - Avoid double-building in `CSRGatherOp.forward` vs backward.  
4. Thread metadata through `ExpertEngineCSR` and tests.
5. Document in `AGENTS.md` + module README.

## 4. Scatter Backward Math Recap

Forward scatter:
$y_t = \sum_{\ell \in \mathcal{S}(t)} w_\ell \cdot a_\ell$.

Backward goals:

- $\text{grad}_a[\ell] = w_\ell \cdot g_{t_\ell}$ (token grad gather + scaling).
- $\text{grad}_w[\ell] = g_{t_\ell} \cdot a_\ell$ (dot product).

### 4.1 Naïve Torch Implementation

```python
grad_token_slots = grad_tokens.index_select(0, indices)          # (E*C, H)
grad_a = grad_token_slots * weights.view(-1, 1)
grad_w = (grad_token_slots * expert_out.view(-1, H)).sum(dim=1)
```

Problems:

- Allocates $(E \cdot C, H)$ intermediate (e.g., $256\text{k} \times 1024 \times 2\text{B} \approx 512\text{ MB}$).
- Reads `grad_tokens` twice.
- Launches multiple kernels (gather, mul, mul, sum).

### 4.2 Fused Kernel Behavior

Single kernel per slot:

1. Precompute base pointers:
   - `grad_base = grad_tokens + t_ℓ * H`
   - `expert_base = grad_expert + ℓ * H`
   - `expert_val_base = expert_out + ℓ * H`
2. For each tile of size `BLOCK_X`:
   - `grad_val = load(grad_base + offsets)`
   - `expert_val = load(expert_val_base + offsets)`
   - `wgrad_acc += dot(grad_val, expert_val)`
   - `output = grad_val * w_ℓ` if weights else `grad_val`
   - `store(output → grad_expert)`
3. After loop, `store(wgrad_acc → grad_weights[ℓ])`

This kernel (`_fused_gather_wgrad`) already exists; we plan to:

- Confirm dtype handling (BF16 inputs, FP32 accumulators, FP32 grad_w).
- Provide wrapper functions for the CSR and sequential backends.

## 5. Gather Backward Math

Keep it CSR-only and think in “tokens” and “slots”:

- Forward CSR gather takes token activations $x \in \mathbb{R}^{N \times H}$ and a table of slot $\rightarrow$ token ids $(e,s) \mapsto t_{e,s}$ and produces an expert-major buffer $y \in \mathbb{R}^{E \times C \times H}$:
  $$
  y_{e,s,h} = x_{t_{e,s}, h}.
  $$
- For backward, we are given $\text{grad}_y$ with the same shape and want $\text{grad}_x \in \mathbb{R}^{N \times H}$.

The rule is simple: each token gradient is the sum of gradients from all slots that pointed to it. Let
$$
\mathcal{S}(t) = \{ (e,s) \mid t_{e,s} = t \}
$$
be the set of slots that chose token $t$. Then
$$
\text{grad}_x[t, h] = \sum_{(e,s) \in \mathcal{S}(t)} \text{grad}_y[e,s,h].
$$

The CSR metadata $(\text{slot\_indices}, \text{slot\_offsets}, \text{slot\_counts})$ is just a packed encoding of all the sets $\mathcal{S}(t)$ in one set of flat arrays. The Triton kernel $\_csr\_scatter\_sum$ implements exactly the formula above by:

- flattening $(e,s)$ to a single “slot” index,
- launching one program per token $t$,
- walking the slice of `slot_indices` that belongs to that token and summing the corresponding rows of $\text{grad}_y$ into $\text{grad}_x[t, :]$.

So for CSR, **gather backward and scatter forward both call $\_csr\_scatter\_sum$**, just with different input tensors. Building the CSR metadata once per forward and reusing it in both places is precisely what we want.

## 6. Sequential-Add / CSR Hybrid

- Sequential kernels currently rebuild metadata internally.  
- Future work: adopt `CSRMetadata` to drive sequential add (token-major program).  
- Backward for sequential scatter would mirror CSR: reuse metadata to gather grads per token, plus weight w.r.t. sequential weights if any.

## 7. Implementation Roadmap

### Phase 1 – Metadata Infrastructure

1. Add `CSRMetadata` dataclass + builder wrapper.  
   - File: `src/ops/csr.py`.
   - Include `.to(device)` helper for potential multi-device use.
2. Update `CSRGatherOp` / `CSRScatterOp` signatures.  
   - Accept `meta: Optional[CSRMetadata] = None`.  
   - Save metadata for backward (no recompute).
3. Update `ExpertEngineCSR.forward_topk`:
   - `csr_meta = build_csr_metadata(topk_indices, n_tokens, self.max_fanout)`  
   - `x_gathered = csr_gather(..., meta=csr_meta)`  
   - `output = csr_scatter_sum(..., meta=csr_meta)`

### Phase 2 – Benchmarks & Tests

1. Replace `build_inverse_indices` in `benchmark/permutation/scatter/benchmark.py` with metadata builder.  
2. Update `test/test_csr_vs_index_add.py`, `test/test_sequential_scatter.py`.
3. Add dedicated test verifying `csr_gather(meta) == csr_gather(None)` etc.

### Phase 3 – Kernel Integration

1. Ensure `_fused_gather_wgrad` is documented as the canonical scatter backward kernel.  
2. Expose helper `scatter_backward_with_weights(grad_tokens, expert_out, indices, weights)` returning both grads.  
3. Evaluate whether CSR backend needs its own fused kernel (token-major). If yes:
   - Launch per token; load `counts` slots; accumulate `grad_w` for each slot via dot product.  
   - Probably not urgent; slot-major kernel is sufficient because gradients are per slot.

### Phase 4 – Docs & Memory

1. Update `AGENTS.md` “CSR metadata” & “Fused kernels” sections.  
2. Summarize math + kernel behavior in `src/models/README.md`.  
3. Record benchmark deltas in `memory/benchmarks/speedup.md`.

## 8. Open Questions

1. **Metadata Caching Across Layers**  
   - For pipelined routing (multiple MoE layers), should we keep metadata in `RouteResult` objects?  
   - Could share between forward/backward passes without rebuild.
2. **Sequential Backward**  
   - If sequential add becomes a production backend, we need analogs of `_csr_scatter_sum` backward and fused `grad_w`.  
   - Should sequential backward simply call CSR metadata builder and reuse kernels? (Probably yes.)
3. **Weightless Path Optimization**  
   - When weights are disabled (e.g., router outputs absent), skip allocating/storing `grad_weights`.
   - Kernel can branch on `APPLY_WEIGHTS` to avoid unnecessary loads.
4. **FP8 / Mixed Precision**  
   - Future support may require wider accumulators; ensure metadata builder tracks dtype so kernels know when to upcast.

## 9. Checklist

- [ ] Implement `CSRMetadata` + builder.
- [ ] Extend `csr_gather` / `csr_scatter_sum` to accept metadata.
- [ ] Update ExpertEngineCSR to build metadata once.  
- [ ] Convert benchmarks/tests to shared metadata path.
- [ ] Document fused scatter backward math & kernel usage.
- [ ] Evaluate sequential backend reuse of metadata.
- [ ] Add regression tests for weight gradients (compare fused kernel vs torch reference).

---

_Prepared by Codex agent — 2025-02-15_
