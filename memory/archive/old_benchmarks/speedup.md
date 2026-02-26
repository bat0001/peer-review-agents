## Report for GEC MLP

Last week (Sep 5-12): 
- Read through nano-vllm
- Learned Triton
- Benchmarking Global Expert Choice (GEC) MLP:
    - 69% Efficiency compared to dense
    - Need Speedup
- Trying to improve the GEC MLP performance
    - Fused Triton kernel
        - Fusing router + top-k?
        - Fusing expert forward pass?
        - Deal with non-contiguous input?
    - MegaBlocks

TODO:
- Fused Triton kernel
- MetaBlocks
- Expert Parallelism
- Inference-time cannot guarantee perfect load balance, need original meta-blocks to do uneven group-GEMM 
- Start scale up analysis

This week (Sep 13-19): 
- Implemented Contrastive Decoding


## Results summary

Config: GPU A5000, torch.compile=True, AMP=bfloat16; Batch size=128, Seq len=1024, Embedding dim=768; Experts=16, ExpertDim=1536, Density=0.125.

| Model | Forward (ms) | Backward (ms) | Peak Mem (MB) | TFLOPS/s | Utilization (%) | Speedup vs Dense |
|---|---:|---:|---:|---:|---:|---:|
| Dense (compiled) | 16.316 | 43.927 | 1925.50 | 37.98 | 34.2 | 1.00x |
| Reference (compiled) | 24.171 | 59.888 | 3309.00 | 25.72 | 23.2 | 0.68x |
| + index_add | 24.064 | 59.610 | 3309.00 | 25.84 | 23.3 | 0.68x |
| - metric expert_usage | 23.771 | 59.270 | 3304.50 | 26.15 | 23.6 | 0.69x |


---

### Notes on attempted changes

- Switched router from `einsum` + reshape to `x_flat @ router_w` and enforced `.contiguous()` before `bmm`. Result: slight regression on A5000 (forward ~+0.5–0.6 ms). Reverted to original `einsum` + `bmm` path.
- Sorted per-expert `topk` indices to improve write locality before `index_add_`. Result: negligible to slightly negative impact; reverted to unsorted order.
| + per-expert sorting | 23.923 | 59.460 | 3308.50 | 25.99 | 23.4 | 0.68x |

## GEC speedups plan

- **Context**: A5000, B=128, T=1024, C=768, n_experts=16, density=0.125 → n_tokens=131,072, k≈16,384/expert. Current bottlenecks: per-expert top-k over all tokens, scattered gathers/writes, many small batched GEMMs, and extra full-tensor passes for metrics.

- **Current Performance**: GEC is 0.68x dense speed (32% slower), with 23.2% vs 34.2% GPU utilization. 12.5% density underutilizes compute units.

### Immediate, low-risk edits (expect 15–30% fwd speedup)

- **Top‑k on logits + reuse values for weights**
  - Compute router logits once on flattened input; call `topk` on logits per expert; compute weights only for the selected items from `topk_values`.
  - Remove full `sigmoid` over `(B*T, n_experts)` and the large `router_probs_selected` gather.
  - Sketch:
```python
# logits instead of probs
router_logits_flat = x_flat @ self.router_w  # (B*T, n_experts)
topk_values, topk_indices = torch.topk(router_logits_flat.t(), k, dim=1)

# later, use weights from selected values only
weights = torch.sigmoid(topk_values).view(n_experts, -1, 1)
```

- **Replace row-wise scatter with index_add_ and use bincount for counts**
  - At `models/gec.py:L123`, replace the expansion-based scatter with a row-wise add.
```python
# Replace
output.scatter_add_(0, permutation_indices.unsqueeze(-1).expand(-1, C), h)
# With
output.index_add_(0, permutation_indices, h)

# Counts
token_counts = torch.bincount(permutation_indices, minlength=n_tokens).float()
```

- **Avoid extra O(B*T*n_experts) metrics pass**
  - Derive `expert_token_counts` from `topk_indices` (each expert has exactly k), and compute `avg_experts_per_token` from the `bincount` above.
```python
expert_token_counts = torch.full((n_experts,), k, device=x.device)
avg_experts = token_counts.mean()
```

- **Prefer matmul over einsum for router; ensure contiguity for GEMMs**
```python
router_logits_flat = x_flat @ self.router_w  # replaces einsum
x_permuted = x_permuted.contiguous()
W1T = self.weight1.transpose(1, 2).contiguous()
W2T = self.weight2.transpose(1, 2).contiguous()
h = torch.bmm(x_permuted, W1T)
h = torch.bmm(h, W2T)
```

### Medium effort (reach ~0.80-0.85x dense speed)

- **Improve write locality**: sort `permutation_indices` (and permute `h` accordingly) within each expert before the `index_add_` to make writes more contiguous.
- **Compiler settings**: try `torch.compile(..., mode="reduce-overhead")`; keep shapes static; avoid data-dependent control flow around `topk` to help fusion.

### High effort (reach ~0.90-0.95x dense speed)

- **Fused Triton kernel**: fuse gather → linear1 → activation → linear2 → scale → scatter into one kernel. This removes intermediate global memory traffic and kernel launches.
- **Grouped GEMM**: use a single grouped matmul (cublasLt/CUTLASS) across experts instead of separate `bmm`s for better occupancy.

### Measurement checklist

- **Re-run** `benchmark/mlp/benchmark.py` with and without compile; record forward/backward means and memory.
- **Validate FLOPs** unchanged where intended; track time ratio and efficiency.
- **Guardrails**: ensure numerics parity vs current code on a few random seeds and inputs (bf16 AMP as in benchmark).

