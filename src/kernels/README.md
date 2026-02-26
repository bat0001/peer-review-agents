# Triton Kernels

Optimized Triton kernels for GEC routing operations (gather/scatter).

## Overview

This module provides hand-tuned Triton kernels that accelerate the GEC routing bottlenecks:

- **gather**: Collect selected tokens into expert-major order
- **scatter_atomic**: Accumulate expert outputs back to tokens using atomic adds
- **fused_gather_wgrad**: Fused gather + weight gradient (2× backward speedup)

## Architecture

The kernels in `balanced.py` combine the best aspects from multiple implementations:
- **Manual**: Simple, well-tuned kernels with explicit intent
- **Codex**: Cleaner API design and loop style
- **Claude**: Fused gather+wgrad for backward pass optimization

### Design Philosophy

1. **Forward pass**: Simple gather/scatter kernels (proven reliability)
2. **Backward pass**: Fused kernel when both gradients needed (common case)
3. **Mixed precision**: All kernels handle BF16 autocast correctly

## Kernel API

### gather

Collect tokens into expert-major order.

```python
from src.kernels import gather

gathered = gather(
    x_flat,      # (n_tokens, hidden_size)
    indices,     # (num_experts * k,) - flat expert-major indices
    weights,     # (num_experts * k,) - optional scaling weights
    num_experts, # number of experts
    k,           # capacity per expert
)
# Returns: (num_experts, k, hidden_size)
```

**Use case**: Forward pass and simple backward (no weight gradients needed).

### scatter_atomic

Accumulate expert outputs back to tokens using atomic adds.

```python
from src.kernels import scatter_atomic

output = scatter_atomic(
    expert_outputs,  # (num_experts, k, hidden_size)
    indices,         # (num_experts * k,)
    n_tokens,        # total number of tokens
)
# Returns: (n_tokens, hidden_size)
```

**Use case**: Forward pass scatter, mirrors PyTorch's `index_add_`.

### fused_gather_wgrad

Fused gather + weight gradient computation for backward pass.

```python
from src.kernels import fused_gather_wgrad

gathered, weight_grad = fused_gather_wgrad(
    x_flat,      # (n_tokens, hidden_size)
    indices,     # (num_experts * k,)
    grad_output, # (num_experts, k, hidden_size)
    num_experts,
    k,
)
# Returns:
#   gathered: (num_experts, k, hidden_size)
#   weight_grad: (num_experts * k,)
```

**Use case**: Backward pass when both input grad and weight grad needed (common case).

## Design Notes

### MegaBlocks contrast

- MegaBlocks routes *tokens to experts* and must radix-sort plus histogram before running kernels.  
- GEC routes *experts to tokens*, so expert-major ordering drops out of routing and our kernels can launch directly over `num_experts × capacity` without extra metadata (`bin_ids`, `bins`, padding, etc.).  
- Balanced capacity is guaranteed; we do not implement spill handling here.

### Gather kernel

- Launch geometry: one Triton program per expert-slot (`num_experts * capacity` grid). Program ID splits into expert/slot indices deterministically.  
- Memory access: scattered reads from the flattened token matrix, coalesced writes to the expert buffer.  
- Optional weights: kernels accept a flat `(num_experts * capacity,)` weight tensor; values load in FP32, multiply the hidden vector, and cast back to the output dtype.  
- Autotune explores block sizes (64/128/256) and warp counts (2/4) keyed on the hidden dimension to keep bandwidth high across model sizes.

### Scatter kernel

- Mirrors the gather launch but writes back with `tl.atomic_add` so overlapping token selections accumulate exactly like `torch.index_add_`.  
- Outputs accumulate into an FP32 buffer; the caller casts back after completion.  
- Host code remains responsible for computing token fanout via `torch.bincount` and normalizing outputs so tokens touched by multiple experts stay averaged.

### Fused gather + weight gradient

- Single pass loads `grad_tokens` and expert activations once, writing `grad_expert` and accumulating weight gradients simultaneously.  
- Autotune extends to 512-wide blocks / 8 warps for larger hidden sizes.  
- Use when both expert-input gradients and gating gradients are required; fall back to `gather` if only one product is needed to avoid overwork.

### Validation checklist

1. Unit test parity against PyTorch reference (`torch.index_add_`, explicit weight-grad dot products) on random tensors.
2. Run `python -m benchmark.permutation` to confirm throughput.
3. After kernel edits, update benchmark deltas in `memory/benchmarks/speedup.md` and mention changes in the commit message/PR notes.

## Benchmark Results

Performance tracking in `memory/benchmarks/speedup.md`.

**When kernels change:**
1. Run benchmarks: `python -m benchmark.permutation gather-backward`
2. Record performance delta in `memory/benchmarks/speedup.md`
3. Document changes in git commit

## File Organization

```
src/kernels/
├── README.md       # This file
├── __init__.py     # Public API exports
└── balanced.py     # Gather/scatter kernel implementations
```

## Development Notes

### Autotuning

Kernels use `@triton.autotune` with configs exploring:
- Block sizes: 64, 128, 256
- Warp counts: 2, 4
- Key: `NUM_COLUMNS` (hidden_size)

Triton selects best config per hidden size during first run.

### Mixed Precision

All kernels handle BF16 autocast:
- Input/output tensors can be BF16
- Internal computation uses native precision
- No explicit casting needed in kernel code

## See Also

- **GEC implementation**: `src/models/README.md`
- **Benchmark suite**: `benchmark/permutation/README.md`
- **Speedup tracking**: `memory/benchmarks/speedup.md`
