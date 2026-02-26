# Plan: Fix GECShared eval dtype mismatch (threshold + normalization_mode=none)

## Context / Failure
- Error reproduces in eval (threshold routing) with `gec_shared` + `normalization_mode=none`.
- Root symptom: `index_add_(): self (Float) and source (BFloat16) must have the same scalar type`.
- The mismatch is created because threshold routing allocates `weights_batched` with `x_flat.dtype` (bf16), but shared weights are created from `fanout` (fp32). `IndexAddScatter` uses `weights_flat.dtype` to choose `accum_dtype`, so routed output becomes bf16, shared output becomes fp32, and `index_add_` fails.

Relevant code snippets:

`src/models/engines/engine.py` (threshold selection dtype):
```python
# _threshold_selection
indices_batched = torch.zeros(n_routed_experts, actual_k_max, device=x_flat.device, dtype=torch.long)
weights_batched = torch.zeros(n_routed_experts, actual_k_max, device=x_flat.device, dtype=x_flat.dtype)
valid_mask = torch.zeros(n_routed_experts, actual_k_max, device=x_flat.device, dtype=torch.bool)
...
weights_batched[expert_idx, :k] = all_weights[active_indices, expert_idx]
```

`src/ops/scatter_backends.py` (accumulation dtype logic):
```python
accum_dtype = weights_flat.dtype if weights_flat.dtype == torch.float32 else h_flat.dtype
h_weighted = h_flat.to(accum_dtype) * weights_flat.unsqueeze(-1)
if shared_flat is not None and shared_weights is not None:
    output = shared_flat.to(accum_dtype) * shared_weights.unsqueeze(-1)
else:
    output = torch.zeros(n_tokens, H, device=h_flat.device, dtype=accum_dtype)
output.index_add_(0, indices_flat, h_weighted)
```

`src/models/gec_shared.py` (normalization_mode=none):
```python
elif normalization_mode == "none":
    normalized_weights = weights_flat
    if engine_shared_weights is None:
        shared_weights = torch.ones_like(fanout)
    else:
        shared_weights = engine_shared_weights
```

## Options (tactical + refactor)

### Option A (tactical, recommended): fix dtype alignment in `IndexAddScatter`
- **Change**: Cast `shared_weights` (and `shared_flat` by multiplication) to `accum_dtype` before building the output tensor.
- **Rationale**: Keeps routed and shared accumulation in the same dtype regardless of routing mode.
- **Impact**: Localized to `IndexAddScatter` only; no routing changes, no config changes.
- **Notes**: `IndexAddScatterFP32` already forces fp32; no change needed there.

### Option B (tactical alternative): keep threshold weights in fp32
- **Change**: In `_threshold_selection`, allocate `weights_batched` with `all_weights.dtype` (fp32) instead of `x_flat.dtype`.
- **Rationale**: Makes `weights_flat` match `fanout` dtype (fp32) so scatter accumulates in fp32.
- **Impact**: Touches routing/selection path; increases memory footprint in threshold mode.

### Option C (refactor): centralize dtype policy for weights
- **Change**: Normalize dtypes in one place (e.g., in `GECSharedMLP.forward` or a utility) so `normalized_weights` and `shared_weights` are explicitly cast to a chosen `weights_dtype` before calling scatter.
- **Rationale**: A clear dtype contract reduces future backend surprises across index_add/CSR.
- **Impact**: Broader code refactor touching routing + normalization; would need broader review.

## Recommended Plan (Option A)
1. **Update `IndexAddScatter` dtype handling**
   - In `src/ops/scatter_backends.py`, cast `shared_weights` to `accum_dtype` before multiplication.
   - Ensure `output` dtype always equals `h_weighted.dtype` so `index_add_` is safe.

   Example patch sketch:
   ```python
   if shared_flat is not None and shared_weights is not None:
       shared_weights = shared_weights.to(accum_dtype)
       output = shared_flat.to(accum_dtype) * shared_weights.unsqueeze(-1)
   else:
       output = torch.zeros(..., dtype=accum_dtype)
   ```

2. **Add regression test (GEC_shared, threshold, normalization_mode=none, bf16)**
   - Extend `test/test_gec_shared_shared_weight.py` with a new test that:
     - Sets `model.routing_mode = "threshold"`, `model.eval()`.
     - Uses `torch.bfloat16` input on CUDA if available.
     - Verifies no dtype error and output dtype matches input dtype.
   - Guard with `if not torch.cuda.is_available(): return` to avoid CI failures on CPU-only environments.

   Example test sketch:
   ```python
   def test_gec_shared_none_threshold_bf16_no_dtype_mismatch():
       if not torch.cuda.is_available():
           return
       config = ModelConfig(..., normalization_mode="none")
       model = GECSharedMLP(config).cuda().eval()
       model.routing_mode = "threshold"
       x = torch.randn(2, 3, config.n_embd, device="cuda", dtype=torch.bfloat16)
       out, _ = model(x)
       assert out.dtype == x.dtype
   ```

3. **(Optional) Add an inline comment**
   - Briefly document that shared weights are cast to `accum_dtype` to align with routed accumulation.

## Validation
- If we run tests locally:
  1. `nvidia-smi` (required before any test).
  2. `python test/test_gec_shared_shared_weight.py`.
- No API changes expected.

## Confirmation Needed
- Please confirm which option you want (A recommended, B or C if you prefer a routing-side or broader refactor).
- Once confirmed, I will apply the edits and run the test (after checking `nvidia-smi`).
