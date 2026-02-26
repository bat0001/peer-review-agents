# Expert Engine

This module provides the core expert computation engine used by GEC and GEC_shared models.

## Architecture Overview

GEC uses a **composition pattern** where:
- Models compose an `ExpertEngine` for routing and expert computation
- Models compose a **scatter backend** for output aggregation
- Engine returns **pre-scatter, unweighted outputs** enabling fused weighted scatter
- Scatter backends apply ALL weights in one fused pass (routed + shared)

```
GEC / GEC_shared (thin wrappers)
    ↓ composes
ExpertEngine (routing + expert computation)
    ↓ returns (h_flat, indices, weights_flat, normalizer, metrics)
Scatter Backend (fused weighting + aggregation)
    ↓
Output
```

**See `memory/design/engine_architecture.md` for detailed design rationale.**

## Single Engine Implementation

All routing and expert computation logic lives in `engine.py`:

```python
class ExpertEngine(nn.Module, RouterMixin):
    """Core expert computation engine.

    Returns pre-scatter, unweighted outputs (h_flat, indices, weights_flat, normalizer, metrics).
    Scatter handled by wrapper via scatter backends (which apply weights).
    """

    def forward_topk(self, x, layer_idx, is_shared):
        """Top-k routing forward pass.

        Returns:
            h_flat: (E*k, C) UNWEIGHTED expert outputs
            indices_batched: (E, k) token indices
            weights_flat: (E*k,) normalized routed weights
            normalizer: (N,) per-token normalizer for shared expert weighting
            metrics: routing metrics
        """

    def forward_threshold(self, x, layer_idx, is_shared):
        """Threshold routing forward pass.

        Returns: Same as forward_topk (padded, with zero weights for invalid)
        """

    def _compute_expert_outputs(self, x_flat, indices_batched):
        """Gather → Expert forward. Returns UNWEIGHTED h_flat (E*k, C)."""
```

## Scatter Backends

Scatter backends live in `src/ops/scatter_backends.py`:

```python
from src.ops.scatter_backends import get_scatter

# In wrapper __init__
self.scatter = get_scatter('index_add')  # or 'csr'

# In wrapper forward
h_flat, indices, weights_flat, normalizer, metrics = self.engine.forward_topk(...)
output = self.scatter(h_flat, indices, n_tokens, weights_flat,
                      shared_flat=shared_output, shared_weights=1/normalizer)
```

### Available Backends

| Backend | File | Strategy | Use Case |
|---------|------|----------|----------|
| `index_add` | `scatter_backends.py` | PyTorch `index_add_` | Default, good torch.compile support |
| `index_add_fp32` | `scatter_backends.py` | PyTorch `index_add_` in FP32 | Higher precision accumulation |
| `csr` | `scatter_backends.py` + `ops/csr.py` | Triton token-parallel | Potentially better for high fanout |
| `csr_optimized` | `scatter_backends.py` + `ops/csr_optimized.py` | Triton with optimized backward | Better L1 cache utilization |

### Fused Weighted Scatter

Both backends apply all weights in one fused pass:

```python
# Scatter applies routed and shared weights together
output = self.scatter(
    h_flat, indices, n_tokens, weights_flat,
    shared_flat=shared_output,       # Unweighted shared expert output
    shared_weights=1.0 / normalizer  # Shared weight = 1/normalizer
)
# Kernel does: output[idx] += h_flat[slot] * weights_flat[slot]
#              output[idx] += shared_flat[idx] * shared_weights[idx]
```

GEC_shared uses this to fuse routed and shared expert weighting.

## Engine API

### Core Methods

```python
def forward_topk(
    self,
    x: Tensor,           # (B, T, C)
    layer_idx: int = 0,
    is_shared: bool = False  # Affects normalization baseline
) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict[str, Tensor]]:
    """Top-k routing.

    Returns:
        h_flat: (E*k, C) UNWEIGHTED expert outputs
        indices_batched: (E, k) token indices
        weights_flat: (E*k,) normalized routed weights
        normalizer: (N,) per-token normalizer for shared expert weighting
        metrics: routing stats
    """

def forward_threshold(
    self,
    x: Tensor,
    layer_idx: int = 0,
    is_shared: bool = False
) -> Tuple[Tensor, Tensor, Tensor, Tensor, Dict[str, Tensor]]:
    """Threshold routing (inference mode).

    Returns: Same as forward_topk (padded, with zero weights for invalid)
    """
```

### State Management

```python
def finalize_cutoff_accumulation(self):
    """Update cutoff EMA at training step boundary."""

def sync_cutoff_state(self) -> Tensor:
    """Return cutoff_ema_raw buffer for DDP syncing."""
```

## Internal Architecture

### What's Inside ExpertEngine

**Owned state**:
- `router`: Linear layer mapping tokens to expert logits
- `expert_weight1`, `expert_weight2`: Per-expert MLP parameters (ParameterList)
- `cutoff_ema_raw`: raw EMA buffer of top-k cutoffs for threshold mode
- `cutoff_ema` (property): effective bias-corrected cutoff used for routing/metrics

**Routing logic**:
- Top-k selection per expert
- Router activation (sigmoid/relu/softmax_k)
- Normalization computation (fanout/select_norm/all_norm)
- Cutoff EMA tracking

**Expert computation** (in `_compute_expert_outputs`):
- Gather tokens by indices
- Batched expert MLP forward (nanochat style: no bias, ReLU²)
- Return flattened UNWEIGHTED h_flat for scatter

### What's Outside ExpertEngine

**Handled by wrapper models** (GEC/GEC_shared):
- Scatter backend composition and invocation (with fused weighting)
- Shared expert computation (GEC_shared only)
- Final output assembly
- Model-level APIs (routing mode switching)

## File Organization

```
src/models/engines/
├── __init__.py     # Exports ExpertEngine
├── engine.py       # Single ExpertEngine implementation
├── README.md       # This file
├── scatter.py      # ScatterMoE-style backend (stub, not integrated)
└── parallel_experts.py  # (empty)

src/ops/
├── scatter_backends.py  # IndexAddScatter, CSRScatter, get_scatter()
├── csr.py              # CSR autograd ops
└── ...
```

## Usage in Wrappers

### GEC (routed only)

```python
class GECMLP(BaseMLP):
    def __init__(self, config):
        self.engine = ExpertEngine(config, n_routed_experts=config.n_experts)
        self.scatter = get_scatter(config.scatter_backend, config.n_experts)

    def forward(self, x, layer_idx=0):
        h_flat, indices_batched, weights_flat, _, metrics = self.engine.forward_topk(x, layer_idx, is_shared=False)
        output = self.scatter(h_flat, indices_batched, n_tokens, weights_flat)
        return output.view(B, T, C), metrics
```

### GEC_shared (with fused weighting)

```python
class GECSharedMLP(BaseMLP):
    def __init__(self, config):
        self.engine = ExpertEngine(config, n_routed_experts=config.n_experts - 1)
        self.scatter = get_scatter(config.scatter_backend, config.n_experts - 1)
        # + shared expert weights

    def forward(self, x, layer_idx=0):
        h_flat, indices_batched, weights_flat, normalizer, metrics = self.engine.forward_topk(x, layer_idx, is_shared=True)

        # Shared expert (unweighted)
        shared_flat = self._shared_expert_forward(x_flat)
        shared_weights = 1.0 / normalizer

        # Fused scatter applies all weights
        output = self.scatter(h_flat, indices_batched, n_tokens, weights_flat,
                              shared_flat=shared_flat, shared_weights=shared_weights)
        return output.view(B, T, C), metrics
```

## Adding a New Scatter Backend

See `memory/design/engine_architecture.md` for instructions on adding new scatter backends.

## Related Documentation

- **Architecture design**: `memory/design/engine_architecture.md`
- **Model README**: `src/models/README.md`
- **Notation (G, E, k formulas)**: `memory/design/notation.md`
- **CSR kernels**: `src/kernels/csr.py`
