# Engine Architecture: Composition with Scatter Backends

**Created**: 2025-11-21
**Updated**: 2025-12-31
**Status**: Implemented

## Overview

The ExpertEngine architecture uses a **composition pattern** where:
1. GEC/GEC_shared models **compose** an ExpertEngine for routed expert logic
2. Models compose **scatter backends** for output aggregation
3. Engine returns **pre-scatter, unweighted outputs** `(h_flat, indices_flat, weights_flat, fanout, shared_weights, metrics)`
4. Scatter backends apply ALL weights in one fused pass (routed + shared)

This design enables:
- Fused weighted scatter (weights applied during aggregation, not before)
- GEC_shared to fuse routed and shared expert weighting in single pass
- Easy scatter backend experimentation without modifying engine code
- Clean separation of routing/computation vs aggregation

## Architecture Layers

```
┌─────────────────────────────────────────┐
│  GEC / GEC_shared (Model wrappers)      │
│  - Shared expert logic (if applicable)  │
│  - Scatter composition (fused weighting)│
│  - Public API (routing mode switching)  │
└──────────────┬──────────────────────────┘
               │ composes
               ↓
┌─────────────────────────────────────────┐
│  ExpertEngine (Single implementation)   │
│  - Router (token → expert logits)       │
│  - Expert weights (W1, W2)              │
│  - Routing logic (topk/threshold)       │
│  - Fanout computation                   │
│  - Cutoff EMA tracking                  │
│  - Returns: (h_flat, indices, weights, fanout, shared_weights, metrics)  │
└─────────────────────────────────────────┘
               │
               ↓ separate composition
┌─────────────────────────────────────────┐
│  Scatter Backends (src/ops/scatter_backends.py) │
│  - IndexAddScatter (torch index_add_)   │
│  - CSRScatter (Triton token-parallel)   │
│  - Apply all weights in fused pass      │
└─────────────────────────────────────────┘
```

## Data Flow

### GEC (routed only)
```python
def forward(self, x, layer_idx):
    # Engine returns unweighted outputs + separate weights + fanout
    h_flat, indices_flat, weights_flat, _fanout, _shared_weights, metrics = self.engine.forward_topk(
        x, layer_idx, is_shared=False
    )

    # Scatter applies weights during aggregation
    output = self.scatter(h_flat, indices_flat, n_tokens, weights_flat)
    return output.view(B, T, C), metrics
```

### GEC_shared (routed + shared, fused weighting)
```python
def forward(self, x, layer_idx):
    # 1. Engine computes routed outputs (unweighted) + weights + fanout (+ optional shared weights)
    h_flat, indices_flat, weights_flat, fanout, engine_shared_weights, metrics = self.engine.forward_topk(
        x, layer_idx, is_shared=True
    )

    # 2. Compute shared expert output (unweighted)
    shared_flat = self._shared_expert_forward(x_flat)
    # shared_weights depends on normalization_mode:
    # - fanout: shared_weights = 1 / (fanout + 1)
    # - none: shared_weights = engine_shared_weights or 1.0 if None
    shared_weights = ...

    # 3. Scatter applies ALL weights in one fused pass
    output = self.scatter(h_flat, indices_flat, n_tokens, weights_flat,
                          shared_flat=shared_flat, shared_weights=shared_weights)
    return output.view(B, T, C), metrics
```

The scatter kernel applies all weights in one fused pass:
- Routed: `output[idx] += h_flat[slot] * weights_flat[slot]`
- Shared: `output[idx] += shared_flat[idx] * shared_weights[idx]`

## Design Rationale

### Why Engine Returns Unweighted Outputs + Weights?

**Previous approach**: Engine applied weights to h_flat before returning

**Problem**: Weighting before scatter prevents fused operations:
```python
# Old: Weights applied before scatter
h_weighted = h_flat * weights  # In engine
output = scatter(h_weighted, indices)  # Just scatter
shared_output = shared_flat / normalizer  # Separate weighting
final = output + shared_output  # Separate addition

# New: All weights applied during scatter (fused)
h_flat, indices, weights_flat, fanout, engine_shared_weights, metrics = engine.forward_topk(...)  # Unweighted
shared_weights = 1.0 / (fanout + 1)  # fanout mode
output = scatter(h_flat, indices, weights_flat,
                 shared_flat=shared_flat, shared_weights=shared_weights)  # Fused!
```

**Benefits of unweighted returns + fused scatter**:
- Single fused pass applies all weights (routed + shared)
- Scatter backend can optimize weight application (e.g., fused multiply-accumulate)
- Engine API is cleaner (compute-only, no weighting)
- For threshold mode: valid_mask applied to weights, not h_flat (avoids filtering)

### Why Scatter Backends as Composition (not Inheritance)?

**Previous approach**: `ExpertEngineCSR` inherited from `ExpertEngine`, overriding `_scatter_expert()`

**Problem**:
- Two engine classes (ExpertEngine, ExpertEngineCSR) with duplicated state
- Backend selection required changing imports in `engines/__init__.py`
- CSR engine diverged from base in ways beyond scatter (bug-prone)

**New approach**: Single ExpertEngine + scatter backends via composition

```python
# In wrapper __init__
self.engine = ExpertEngine(config, n_routed_experts)
self.scatter = get_scatter(config.scatter_backend, max_fanout)

# In wrapper forward
h_flat, indices, weights_flat, normalizer, metrics = self.engine.forward_topk(...)
output = self.scatter(h_flat, indices, n_tokens, weights_flat, ...)
```

**Benefits**:
- Single source of truth for engine logic
- Backend selection per-wrapper (GEC could use index_add, GEC_shared could use CSR)
- Scatter backends are stateless and simple
- Easy to add new backends (~30 lines each)

## Scatter Backend API

All scatter backends implement this interface:

```python
class ScatterBackend:
    def __call__(
        self,
        h_flat: Tensor,             # (E*k, H) - UNWEIGHTED expert outputs
        indices_batched: Tensor,    # (E, k) - token indices
        n_tokens: int,              # Total tokens (N)
        weights_flat: Tensor,       # (E*k,) - routed expert weights
        shared_flat: Optional[Tensor] = None,    # (N, H) - UNWEIGHTED shared output
        shared_weights: Optional[Tensor] = None, # (N,) - shared weights = 1/normalizer
    ) -> Tensor:
        """Scatter expert outputs to tokens with fused weighting.

        Applies all weights in one fused pass:
        - Routed: output[idx] += h_flat[slot] * weights_flat[slot]
        - Shared: output[idx] += shared_flat[idx] * shared_weights[idx]

        Returns: (N, H) token outputs
        """
```

### IndexAddScatter (Default)

Uses PyTorch's `index_add_` with fused weight application.

```python
class IndexAddScatter:
    def __call__(self, h_flat, indices_batched, n_tokens, weights_flat,
                 shared_flat=None, shared_weights=None):
        # Apply weights to routed outputs
        h_weighted = h_flat * weights_flat.unsqueeze(-1)

        # Initialize with weighted shared (if provided)
        if shared_flat is not None and shared_weights is not None:
            output = shared_flat * shared_weights.unsqueeze(-1)
        else:
            output = torch.zeros(n_tokens, H, ...)

        output.index_add_(0, indices_batched.view(-1), h_weighted)
        return output
```

**Characteristics**:
- Slot-level parallelism (per expert-token slot writes)
- Native PyTorch (good torch.compile support)
- Simple and readable

### CSRScatter (Token-parallel)

Uses custom Triton kernel with CSR (Compressed Sparse Row) format.

```python
class CSRScatter:
    def __init__(self, max_fanout: int):
        self.max_fanout = max_fanout

    def __call__(self, h_flat, indices_batched, n_tokens, weights_flat,
                 shared_flat=None, shared_weights=None):
        # Build CSR metadata
        slot_indices, slot_offsets, slot_counts = kernels.build_slot_indices(
            indices_batched, num_tokens=n_tokens, max_experts=self.max_fanout
        )
        return csr_scatter_sum(
            h_flat, indices_batched,
            num_tokens=n_tokens,
            max_experts=self.max_fanout,
            slot_indices=slot_indices,
            slot_offsets=slot_offsets,
            slot_counts=slot_counts,
            weights_flat=weights_flat,
            shared_flat=shared_flat,
            shared_weights=shared_weights,
        )
```

**Characteristics**:
- Token-level parallelism (each token sums its contributing slots)
- Custom Triton kernel with autograd support
- Fully fused weighting (routed + shared in single kernel pass)
- CSR metadata overhead but potentially better for high fanout

### CSR Metadata Format

The CSR (Compressed Sparse Row) format enables token-parallel scatter by precomputing which slots contribute to each token:

```python
slot_indices, slot_offsets, slot_counts = build_slot_indices(
    indices_batched,  # (E, k) token indices
    num_tokens=N,
    max_experts=max_fanout
)
```

| Array | Shape | Description |
|-------|-------|-------------|
| `slot_indices` | `(N, max_fanout)` | For token t, `slot_indices[t, :]` lists contributing slot indices |
| `slot_offsets` | `(N,)` | Unused in current impl (implicit from slot_counts) |
| `slot_counts` | `(N,)` | Number of experts contributing to each token |

**Token-parallel vs Slot-parallel**:
- Slot-parallel (index_add): Each slot writes to its token → atomic contention
- Token-parallel (CSR): Each token reads its contributing slots → no contention

**Weight application during scatter**:
```python
# Per-slot: output[t] += h_flat[slot] * weights_flat[slot]
# Shared:   output[t] += shared_flat[t] * shared_weights[t]
```

All weights applied in one fused kernel pass, avoiding separate multiply operations.

## Engine API

The single `ExpertEngine` class provides:

### Core Methods

```python
def forward_topk(
    self,
    x: Tensor,           # (B, T, C)
    layer_idx: int = 0,
    is_shared: bool = False
) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict[str, Tensor]]:
    """Top-k routing forward pass.

    Returns:
        h_flat: (E*k, C) UNWEIGHTED expert outputs
        indices_batched: (E, k) token indices
        weights_flat: (E*k,) normalized routed weights
        normalizer: (N,) per-token normalizer for shared expert weighting
        metrics: routing metrics
    """

def forward_threshold(
    self,
    x: Tensor,
    layer_idx: int = 0,
    is_shared: bool = False
) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict[str, Tensor]]:
    """Threshold routing forward pass.

    Returns: Same as forward_topk (padded to E*k, with zero weights for invalid)
    Note: valid_mask is applied to weights, not h_flat
    """

def _compute_expert_outputs(
    self,
    x_flat: Tensor,         # (n_tokens, C)
    indices_batched: Tensor,  # (E, k)
) -> Tensor:
    """Gather → Expert forward. Returns UNWEIGHTED h_flat (E*k, C)."""
```

### State Management

```python
def finalize_cutoff_accumulation(self):
    """Update cutoff EMA at training step boundary."""

def sync_cutoff_state(self) -> Tensor:
    """Return cutoff_ema for DDP syncing."""
```

## Configuration

Scatter backend selection via config:

```yaml
# configs/mlp/gec.yaml
model:
  scatter_backend: 'index_add'  # or 'index_add_fp32', 'csr', 'csr_optimized'
  moe_max_fanout: 8  # Required for CSR backend
```

```python
# In wrapper __init__
backend = getattr(config, 'scatter_backend', 'index_add')
max_fanout = getattr(config, 'moe_max_fanout', config.n_experts)
self.scatter = get_scatter(backend, max_fanout)
```

## Files

| File | Purpose |
|------|---------|
| `src/models/engines/engine.py` | Single ExpertEngine implementation |
| `src/models/engines/__init__.py` | Exports ExpertEngine |
| `src/ops/scatter_backends.py` | IndexAddScatter, CSRScatter, get_scatter() |
| `src/ops/csr.py` | CSR autograd ops (CSRScatterOp, csr_scatter_sum) |
| `src/kernels/csr.py` | CSR Triton kernels |

## Adding a New Scatter Backend

1. Add class to `src/ops/scatter_backends.py`:

```python
class MyScatter:
    def __init__(self, some_config):
        self.config = some_config

    def __call__(self, h_flat, indices_batched, n_tokens, weights_flat,
                 shared_flat=None, shared_weights=None):
        # Apply routed weights
        h_weighted = h_flat * weights_flat.unsqueeze(-1)

        # Initialize with weighted shared (if provided)
        if shared_flat is not None and shared_weights is not None:
            output = shared_flat * shared_weights.unsqueeze(-1)
        else:
            output = torch.zeros(n_tokens, h_flat.shape[1], ...)

        # Your scatter implementation
        my_custom_scatter(output, h_weighted, indices_batched)
        return output
```

2. Update `get_scatter()` factory function
3. Add config option and test

## Summary

**Key principles**:
1. **Single engine** - One ExpertEngine handles all routing/computation
2. **Unweighted returns** - Engine returns `(h_flat, indices, weights_flat, normalizer, metrics)`
3. **Fused weighted scatter** - All weights (routed + shared) applied during scatter
4. **Scatter via composition** - Wrappers compose scatter backends
5. **Stateless backends** - Scatter classes are simple and composable

**Benefits**:
- Clean separation of concerns (routing vs aggregation)
- Flexible scatter backend selection per-wrapper
- Fused weighting (single pass for routed + shared)
- Simple to add new scatter backends
- Single source of truth for engine logic
