# EC_shared: Expert Choice with Shared Expert

**Created**: 2025-10-27
**Status**: Implemented and tested

## Overview

`ec_shared` combines two routing strategies:
- **Chunked routing** from Expert Choice (EC)
- **Shared expert architecture** from GEC_shared

This provides flexible control over routing granularity while maintaining the benefits of a dedicated shared expert.

## Motivation

**Why not merge into gec_shared?**
- Keeps code simple and modular
- Inheritance approach minimizes code duplication
- Chunking is optional (routing_chunk_seqs=null falls back to global routing)
- Separate model type makes experiments clearer

**Why add chunked routing?**
- **Per-sequence routing**: Each sequence independently routes tokens to experts
- **Reduced variance**: Smaller chunks → more consistent per-expert load within chunk
- **Causal routing compatibility**: Chunk-based cutoff averaging for threshold inference

## Implementation

### Architecture

```
ECSharedMLP (ec_shared.py)
  ├── Inherits from GECSharedMLP
  ├── Overrides: forward_topk()  (adds chunked routing)
  └── Inherited: forward_threshold(), _shared_expert_forward()
```

### Key Design Choices

1. **Inheritance over duplication**
   - Only 130 lines vs ~400 if copied from gec_shared
   - Fallback to parent when `routing_chunk_seqs=None`
   - All shared expert logic reused

2. **Chunking mechanism** (from ec.py:92-145)
   ```python
   chunk_seqs = routing_chunk_seqs or B  # None → global routing
   n_chunks = B // chunk_seqs
   chunk_size = chunk_seqs * T
   k = chunk_size * (G-1) // (G * E)  # Per-chunk k
   ```

3. **Cutoff EMA averaging**
   - Top-k per (chunk, expert) → `cutoffs: (n_chunks, n_routed_experts)`
   - Average across chunks: `avg_cutoffs = cutoffs.mean(dim=0)`
   - Threshold routing uses averaged cutoff_ema

4. **GEMM geometry preserved**
   - Chunk indices adjusted to global positions with offsets
   - Group by expert: `(n_experts, n_chunks, k)` → `(n_experts, n_chunks*k)`
   - Same batched matmuls as global routing

## Configuration

### Config file: `configs/mlp/ec_shared.yaml`

```yaml
model:
  model_type: ec_shared
  granularity: 2
  expansion: 8
  routing_chunk_seqs: null  # null=global, 1=per-seq, 2/4/8/16=per-N-seqs
  router_activation: sigmoid
  normalization_mode: fanout
```

### Usage examples

```bash
# Global routing (same as gec_shared)
python train.py mlp=ec_shared

# Per-sequence routing
python train.py mlp=ec_shared model.routing_chunk_seqs=1

# Per-4-sequence routing
python train.py mlp=ec_shared model.routing_chunk_seqs=4
```

## Testing Results

### Unit Tests (2025-10-27)

✓ Model creation: `ec_shared` registered and validated
✓ Global routing: `routing_chunk_seqs=None` → forward pass successful
✓ Chunked routing: `routing_chunk_seqs=1,2,4` → forward pass successful
✓ Training: `+experiment=debug training.max_steps=2` → exit code 0

### Test command

```bash
CUDA_VISIBLE_DEVICES=9 python train.py mlp=ec_shared +experiment=debug training.max_steps=5
```

## Files Modified

| File | Changes | Lines |
|------|---------|-------|
| `src/models/ec_shared.py` | New file (inherits GECSharedMLP, adds chunked routing) | +130 |
| `src/models/model_base.py` | Add `ec_shared` to validation and `_get_mlp_class()` | +6 |
| `src/config.py` | Add `ec_shared` to model type validation | +1 |
| `configs/mlp/ec_shared.yaml` | New config file | +30 |

**Total**: ~167 lines added (vs ~400+ if implemented from scratch)

## Relation to Existing Models

| Model | Routing | Shared Expert | Chunking |
|-------|---------|---------------|----------|
| `gec` | Global top-k | No | No |
| `gec_shared` | Global top-k | Yes | No |
| `ec` | Chunked top-k | No | Yes |
| **`ec_shared`** | **Chunked top-k** | **Yes** | **Yes** |

## Design Rationale

### Separate file vs merging into gec_shared

**Option A: Merge chunking into gec_shared.py** (rejected)
- Adds ~20 lines of if/else branching to `forward_topk()`
- Conflates two orthogonal features (shared expert + chunking)
- Harder to ablate or compare

**Option B: Separate ec_shared.py with inheritance** (chosen)
- Clear separation of concerns
- Minimal code (~130 lines total)
- Easy to maintain and extend
- Natural model taxonomy (ec vs ec_shared, gec vs gec_shared)

### Fallback behavior

When `routing_chunk_seqs=None`:
```python
if self.routing_chunk_seqs is None:
    return super().forward_topk(x, layer_idx)
```

This ensures:
- Zero overhead when chunking not used
- Identical behavior to `gec_shared` for global routing
- Clear intent in code

## Future Work

- [ ] Benchmark chunked vs global routing on actual training runs
- [ ] Investigate optimal chunk sizes for different batch sizes
- [ ] Test threshold routing with chunked-trained models
- [ ] Consider adding trainable threshold support (if needed)

## References

- `src/models/ec.py`: Original chunked routing implementation
- `src/models/gec_shared.py`: Parent class (shared expert architecture)
- CLAUDE.md: GEC notation (G, E, k formulas)
