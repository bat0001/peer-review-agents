# Router Metrics Reference

## Overview

Comprehensive reference for routing metrics tracked across all MoE/GEC models (GEC, EC, GEC_shared).

**Implementation**: All metrics computed in `RouterMixin.compute_routing_metrics()` (src/models/model_base.py)

## Design Principles

1. **Temporal > Spatial**: Track step-to-step changes (training dynamics), not within-batch variation (sampling noise)
2. **Representative layers**: Track detailed temporal history at 5 layers to reduce memory overhead
3. **Unified metrics**: All models use identical metric names (no model prefixes) for direct comparison
4. **Code sharing**: Common computation in RouterMixin base class eliminates duplication
5. **Tensor types**: All metrics are `torch.Tensor` (scalars or vectors), never Python floats - enables aggregation via `torch.stack()`

---

## Metric Categories

### Common Metrics (ALL Models)

These metrics are computed by **all routing models** (GEC, EC, GEC_shared) with **identical names** (no model-specific prefixes).

**Model identification**: Model type is specified in wandb run config/name, allowing direct comparison of metrics across models.

#### Global Routing Metrics

| Metric | Shape | Description |
|--------|-------|-------------|
| `expert_usage` | `(n_experts,)` | Fraction of tokens processed by each expert |
| `avg_experts_per_token` | scalar | Average fanout (number of experts per token) |
| `max_experts_per_token` | scalar | Maximum fanout (worst-case token overlap) |
| `tokens_with_no_expert` | scalar | Fraction of tokens with zero expert coverage |
| `tokens_with_1_expert` | scalar | Fraction with exactly 1 expert (no overlap) |
| `tokens_with_2+_experts` | scalar | Fraction with 2+ experts (has overlap) |

#### Cutoff Tracking

| Metric | Shape | Description |
|--------|-------|-------------|
| `cutoffs` | `(n_experts,)` | Current routing cutoffs (averaged across chunks if applicable) |
| `cutoff_ema` | `(n_experts,)` | Exponential moving average of cutoffs (decay=0.99) |
| `cutoff_abs_deviation` | scalar | `abs(cutoffs - cutoff_ema).mean()` - measures instant vs smoothed deviation |

**Why no CV?** Coefficient of variation breaks when mean ≤ 0 (router logits are often negative).

#### Router Statistics

| Metric | Shape | Description |
|--------|-------|-------------|
| `activation_weight_mean` | scalar | Mean of activated router weights (post-sigmoid/softmax) |
| `activation_weight_std` | scalar | Std of activated router weights |
| `activation_weight_max` | scalar | Maximum activated weight (most confident selection) |
| `activation_weight_min` | scalar | Minimum activated weight (least confident selection) |
| `router_logit_mean` | scalar | Mean router logit (pre-activation, can be negative) |
| `router_logit_std` | scalar | Std router logit (measures routing confidence) |

#### Representative Layer Metrics

**Representative layers**: `{0, n_layer//4, n_layer//2, 3*n_layer//4, n_layer-1}` (5 layers total)

Tracked at 5 layers to reduce memory overhead while preserving per-layer visibility.

| Metric | Shape | Description |
|--------|-------|-------------|
| `repr_L{i}_E0_cutoff` | scalar | Expert 0 cutoff at layer i (instant value) |
| `repr_L{i}_E0_cutoff_ema` | scalar | Expert 0 cutoff EMA at layer i |
| `repr_L{i}_E0_cutoff_temporal_std` | scalar | Std of cutoff over last 100 steps (after warmup) |
| `repr_L{i}_E0_cutoff_delta` | scalar | `abs(cutoff_t - cutoff_{t-1})` - single-step absolute change |

**Why expert 0?** Representative tracking - expert 0 behavior generalizes to other experts.

**Memory overhead**: `100 steps × n_experts × 4 bytes × 5 layers` ≈ 16KB for 8 experts

**Temporal metrics computed after warmup** (default: 10 steps). Before warmup, only instant cutoffs logged.

---

### Model-Specific Behavior

While all models use **identical metric names**, some models compute them differently:

#### GEC_shared (GEC with Shared Expert)

GEC_shared has one shared expert (always active for all tokens) + routed experts (selected via GEC).

**How the shared expert affects common metrics:**

| Common Metric | GEC_shared Behavior |
|---------------|---------------------|
| `expert_usage` | First element = 1.0 (shared always active), rest = routed expert fractions |
| `avg_experts_per_token` | Includes shared: `1.0 + avg_routed` (always ≥ 1.0) |
| `cutoffs` / `cutoff_ema` | Only for routed experts (shape: `n_routed_experts = n_experts - 1`) |

#### EC (Expert Choice with Configurable Routing Granularity)

EC supports chunking via `routing_chunk_seqs` config parameter. Chunking affects how cutoffs are computed:

| Config | Behavior |
|--------|----------|
| `routing_chunk_seqs=None` | Global routing (single chunk), identical to GEC |
| `routing_chunk_seqs=N` | Per-N-sequence routing, cutoffs averaged across chunks |

**Note**: `n_chunks` is **not logged** as a metric (it's in the config). All cutoff metrics are averaged across chunks if applicable.

---

## Deprecated Metrics

### Removed in This Version

| Metric | Reason |
|--------|--------|
| `ec_repr_L{i}_E0_cutoff_std` | Spatial metric (chunk-to-chunk variance) - not actionable, replaced by temporal std |
| `ec_n_chunks` | Config parameter, not a training metric - already in wandb config |
| `gec_shared_avg_routed_experts_per_token` | Redundant - can compute from `avg_experts_per_token - 1.0` |
| `gec_shared_max_routed_experts_per_token` | Redundant - same as `max_experts_per_token` for GEC_shared |
| `gec_shared_tokens_with_no_routed_expert` | Redundant - same as `tokens_with_no_expert` for GEC_shared |

**Why remove prefixes?**
- All models track the same concepts (fanout, cutoffs, weights)
- Direct comparison in wandb (overlay GEC vs EC runs)
- Model type identified by run name/config, not metric prefix

---

## Implementation Strategy

### RouterMixin: Unified Metrics Computation

**File**: `src/models/model_base.py`

Add method to `RouterMixin` class:

```python
def compute_routing_metrics(
    self,
    cutoffs: torch.Tensor,           # (n_experts,) or (n_chunks, n_experts)
    cutoff_ema: torch.Tensor,        # (n_experts,)
    weights: torch.Tensor,           # Activated router weights (flattened)
    router_logits_flat: torch.Tensor, # (n_tokens, n_experts)
    token_fanout: torch.Tensor,      # (n_tokens,) - expert count per token
    expert_usage: torch.Tensor,      # (n_experts,) - already computed
    layer_idx: int,                  # Current layer index
    n_layer: int,                    # Total layers
) -> Dict[str, torch.Tensor]:
    """Compute all common routing metrics.

    Returns dict with all metrics listed in "Common Metrics" section above.
    All metric names are identical across models (no prefixes).

    Temporal metrics require buffers initialized in __init__:
    - cutoff_history_L{i}: (temporal_window, n_experts)
    - history_idx_L{i}: scalar tensor
    - prev_cutoff_L{i}: (n_experts,)
    """
```

**Benefits:**
- All models call same method → consistency
- ~200 lines of duplicated code → ~80 lines in mixin
- Single source of truth for metric definitions

### Model Requirements

All models (GEC, EC, GEC_shared) must:

1. **Initialize representative layer tracking** (`__init__`):
   ```python
   self.repr_layers = {0, config.n_layer//4, config.n_layer//2, 3*config.n_layer//4, config.n_layer-1}
   self.temporal_window = getattr(config, 'temporal_window', 100)
   self.temporal_warmup = getattr(config, 'temporal_warmup', 10)

   # Temporal buffers for representative layers
   for layer in self.repr_layers:
       self.register_buffer(f'cutoff_history_L{layer}', torch.zeros(self.temporal_window, n_experts))
       self.register_buffer(f'history_idx_L{layer}', torch.tensor(0))
       self.register_buffer(f'prev_cutoff_L{layer}', torch.zeros(n_experts))
   ```

2. **Accept `layer_idx` parameter** in `forward()`:
   ```python
   def forward(self, x: torch.Tensor, layer_idx: int = 0) -> Tuple[torch.Tensor, Dict]:
   ```

3. **Call unified method** before returning:
   ```python
   # Compute common metrics (all models)
   common_metrics = self.compute_routing_metrics(
       cutoffs=cutoffs_avg,  # Average across chunks if applicable
       cutoff_ema=self.cutoff_ema,
       weights=weights.view(-1),
       router_logits_flat=router_logits_flat,
       token_fanout=token_fanout,
       expert_usage=expert_usage,
       layer_idx=layer_idx,
       n_layer=self.config.n_layer,
   )
   metrics.update(common_metrics)

   # No model-specific metrics to add
   return output, metrics
   ```

### Implementation Requirements

All models (GEC, EC, GEC_shared) implement metrics via the same flow:

#### Model `__init__` Requirements
- Initialize `repr_layers = {0, n_layer//4, n_layer//2, 3*n_layer//4, n_layer-1}`
- Initialize temporal buffers for each representative layer:
  - `cutoff_history_L{i}`: (temporal_window, n_experts) circular buffer
  - `history_idx_L{i}`: current buffer index
  - `prev_cutoff_L{i}`: previous step cutoffs for delta computation

#### Model `forward()` Requirements
- Accept `layer_idx` parameter (passed by TransformerBlock)
- Call `self.compute_routing_metrics()` with required tensors
- Return unified metrics dict (no model-specific prefixes)

**Note**: GEC_shared adjusts `token_fanout` to include shared expert (+1.0) before calling unified method.

---

## Configuration

Optional parameters in model configs (all have sensible defaults):

```yaml
model:
  temporal_window: 100      # History buffer size for temporal metrics (default: 100)
  temporal_warmup: 10       # Min steps before computing temporal stats (default: 10)
```

**Defaults**: If omitted, `temporal_window=100` and `temporal_warmup=10` are used.

---

## Temporal vs Spatial Metrics

### Temporal Metrics (Tracked)

**Definition**: Variation across training steps (step-to-step changes)

**Purpose**: Diagnose training stability, detect routing drift/collapse

**Actionable**: High temporal variance → unstable training → adjust hyperparameters (LR, warmup, etc.)

**Examples**:
- `cutoff_temporal_std`: Std of cutoff over last 100 steps
- `cutoff_delta`: Single-step absolute change
- `cutoff_abs_deviation`: Deviation from EMA

### Spatial Metrics (Not Tracked)

**Definition**: Variation within a single forward pass (chunk-to-chunk, batch-to-batch)

**Purpose**: Mostly sampling noise or design artifacts (chunking strategy)

**Not actionable**: Doesn't inform training dynamics

**Examples** (deprecated):
- ~~`cutoff_std` across chunks~~: Replaced by averaging (`cutoffs.mean(dim=0)`)
- ~~Batch-to-batch variance~~: Not logged (already handled by temporal tracking)

---

## Aggregation Notes

Current aggregation in `BaseGPT.forward()` (model_base.py ~441-446):

```python
all_metrics = {}
for i, block in enumerate(self.blocks):
    x, block_metrics = block(x)
    for k, v in block_metrics.items():
        if k not in all_metrics:
            all_metrics[k] = []
        all_metrics[k].append(v)

# Aggregate
aggregated_metrics = {}
for k, v_list in all_metrics.items():
    if v_list:
        aggregated_metrics[k] = torch.stack(v_list).mean()
```

**Behavior**:
- **Scalar metrics** (e.g., `avg_experts_per_token`): Averaged across all layers ✓
- **Vector metrics** (e.g., `expert_usage`, `cutoffs`): Averaged across all layers (loses per-layer info)
- **Representative layer metrics** (e.g., `repr_L{i}_*`): Only present for representative layers (5 per model)

**Result**: Representative layer metrics preserve per-layer detail where needed, global averages for scalars.

---

## Metric Type Requirements

**Critical**: All metrics MUST be `torch.Tensor` (not Python floats/ints) to enable aggregation with `torch.stack()`.

### Implementation Pattern

```python
# ✓ CORRECT: Keep as tensor
metrics['avg_experts_per_token'] = token_fanout.mean()  # torch.Tensor (scalar)
metrics['expert_usage'] = expert_token_counts / n_tokens  # torch.Tensor (vector)

# ✗ WRONG: Converts to Python float
metrics['avg_experts_per_token'] = token_fanout.mean().item()  # float - breaks aggregation!
```

### Gradient Detachment

**Do NOT use `.detach()` or `.item()` on routing metrics** - they're already non-differentiable.

**Why metrics have no gradients**:
- Computed from `torch.zeros()` (no `requires_grad`)
- Boolean masks (`router_logits >= threshold`) break gradient chain
- Count operations (`.sum()` on boolean) produce non-grad tensors

```python
# These already have requires_grad=False (no .detach() needed)
token_fanout = torch.zeros(n_tokens)  # requires_grad=False
above_mask = router_logits >= threshold  # Boolean → requires_grad=False
n_above = above_mask.sum()  # requires_grad=False
```

**Exception**: Visualization data that directly uses router logits MAY need `.detach()`:
```python
# Visualization data (not aggregated metrics)
metrics['layer_data'] = {
    'weights': weights_from_logits.detach(),  # weights_from_logits may have gradients
    'fanout': token_fanout.detach(),  # Redundant but harmless
}
```

### Python Scalar Divisions

**Python int/int → Python float** (not a tensor). Must wrap in `torch.tensor()`:

```python
# ✗ WRONG: Results in Python float
capacity_overflow = 5  # int
n_experts = 8  # int
metrics['overflow_rate'] = capacity_overflow / n_experts  # 0.625 (float) - breaks aggregation!

# ✓ CORRECT: Wrap in torch.tensor()
metrics['overflow_rate'] = torch.tensor(
    capacity_overflow / n_experts,
    device=x.device
)
```

**When wrapping is needed**:
- Both operands are Python `int` → division returns `float`
- Either operand is `torch.Tensor` → division returns `torch.Tensor` (no wrapping needed)

### Logging Layer Handles Conversion

**Metrics stay as tensors internally** - conversion to Python floats happens at logging time:

```python
# train.py (logging layer)
for k, v in metrics.items():
    if hasattr(v, 'item'):
        logged_value = v.item()  # Convert tensor → float for wandb
```

**Benefit**: Metrics can be aggregated with `torch.stack()`, then converted to floats only when logged.

### Bug Reference

See `memory/bugs/metrics_aggregation_bug4.md` for historical context:
- Incorrect use of `.item()` broke aggregation in `model_base.py`
- Fixed by removing `.item()` and wrapping Python divisions

---

## Example: Full Metric Set (All Models)

All models (GEC, EC, GEC_shared) produce the same metric names:

```python
# Global routing (averaged across all layers)
'expert_usage': tensor([0.125, 0.125, 0.125, ...])  # (8,)
'avg_experts_per_token': tensor(1.0)
'max_experts_per_token': tensor(2.0)
'tokens_with_no_expert': tensor(0.0)
'tokens_with_1_expert': tensor(1.0)
'tokens_with_2+_experts': tensor(0.0)

# Cutoffs (averaged across all layers)
'cutoffs': tensor([0.5, 0.6, 0.4, ...])  # (8,)
'cutoff_ema': tensor([0.52, 0.58, 0.42, ...])  # (8,)
'cutoff_abs_deviation': tensor(0.03)

# Router statistics (averaged across all layers)
'activation_weight_mean': tensor(0.65)
'activation_weight_std': tensor(0.12)
'activation_weight_max': tensor(0.95)
'activation_weight_min': tensor(0.15)
'router_logit_mean': tensor(0.02)
'router_logit_std': tensor(0.85)

# Representative layers (5 layers × 4 metrics each = 20 entries)
'repr_L0_E0_cutoff': tensor(0.48)
'repr_L0_E0_cutoff_ema': tensor(0.50)
'repr_L0_E0_cutoff_temporal_std': tensor(0.05)  # After warmup
'repr_L0_E0_cutoff_delta': tensor(0.02)         # After warmup

'repr_L3_E0_cutoff': tensor(0.55)
'repr_L3_E0_cutoff_ema': tensor(0.53)
'repr_L3_E0_cutoff_temporal_std': tensor(0.08)
'repr_L3_E0_cutoff_delta': tensor(0.03)

# ... (repr_L6, repr_L9, repr_L11)
```

**Total**: ~34 metrics (6 global + 3 cutoff + 6 router + 20 representative layer)

**Comparison in wandb**: Overlay multiple runs (GEC vs EC vs GEC_shared) to compare the same metrics across models.

---

## Testing & Validation

### Metric Consistency Tests

To verify metrics work correctly across all models:

1. **Cross-model consistency**: Run same forward pass on GEC/EC/GEC_shared
   - All should produce identical metric names
   - Values should be comparable (accounting for model differences like shared expert)

2. **Temporal warmup**: Temporal metrics (`*_temporal_std`, `*_delta`) only appear after `temporal_warmup` steps
   - Before warmup: Only instant cutoffs logged
   - After warmup: Full temporal metrics available

3. **Representative layers**: Only 5 layers emit `repr_L{i}_*` metrics
   - Layers: 0, n_layer//4, n_layer//2, 3*n_layer//4, n_layer-1
   - Memory overhead: ~16KB for 8 experts

4. **Buffer updates**: History buffers use circular indexing
   - Size: `temporal_window` (default 100)
   - Oldest entries overwritten when full

### Validation Example

Test temporal metrics with synthetic fluctuation:

```python
# Inject sawtooth pattern: cutoff oscillates ±0.1 every step
expected_std = 0.1 / sqrt(2)  # For uniform oscillation
assert abs(measured_std - expected_std) < 0.01
```

### Integration Testing

Run small training (100 steps) to verify:
- All common metrics present in logs
- Temporal metrics evolve over time
- Wandb hierarchy correct (see `design/logging_architecture.md`)

---

## Design Rationale

### Why Unified Metrics?

| Decision | Rationale |
|----------|-----------|
| **Same metric names across models** | Direct comparison in wandb (overlay GEC vs EC runs), cleaner hierarchy |
| **No model prefixes** | Model type identified by run name/config, not metric names |
| **RouterMixin implementation** | 75% code reduction (~600 lines → ~120), single source of truth |
| **Representative layers (5)** | Balance detail vs memory (16KB vs 192KB for all 24 layers) |
| **Temporal over spatial** | Actionable insights (training dynamics) vs noise (sampling variation) |

### Architecture Benefits

- **Consistency**: All models compute identical ~35 metrics
- **Code sharing**: Common logic in RouterMixin base class
- **Extensibility**: Add new metrics once, available everywhere
- **Memory efficiency**: Temporal buffers only at 5 representative layers
- **Comparison**: Direct overlay of different model runs in wandb

### Key Tradeoffs

- **No per-expert expansion**: Vector metrics logged as arrays (not E0, E1, ...) to avoid metric explosion
- **Representative layers only**: Full per-layer detail at 5 layers, averages for others
- **Temporal warmup**: First 10 steps lack temporal metrics (buffer filling)
