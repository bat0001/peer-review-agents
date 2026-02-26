# Models Module

This module contains all model implementations for the GEC project.

## Model Types

The project supports eight model types, configured via `model_type` in config files:

- **`dense`** - Standard transformer with dense FFN layers
- **`gec`** - Global Expert Choice (GEC) with routed experts only
- **`gec_shared`** - GEC with routed experts + one shared expert
- **`gec_shared_capacity`** - GEC shared with capacity-constrained trainable threshold routing
- **`ec`** - Expert Choice with configurable routing granularity (extends GEC)
- **`ec_shared`** - EC with shared expert (combines chunked routing + shared expert)
- **`scattermoe_tc`** (alias: **`tc`**) - ScatterMoE-backed token-choice MoE (top-k experts per token)
- **`tc_shared`** - ScatterMoE-backed token-choice MoE with a shared expert

## Expert Parallel (EP) Checkpoints

EP checkpoints should store **contiguous** per-layer expert indices
`expert_weight{1,2}.0..n_routed_experts-1`. If you encounter older EP checkpoints
with gapped indices, repair them with `script/archived/fix_ep_checkpoint_indices.py`.

## ScatterMoE Token-Choice (scattermoe_tc / tc)

Token-choice routing selects **top-k experts per token** (k derived from G/E) and
executes expert MLPs via ScatterMoE Triton kernels.

Key points:
- **top_k is derived**: `top_k = n_experts // expansion = granularity`
- **No normalization** of gates (raw activated weights are used)
- `softmax_k` is **not** supported for token-choice (selection is per token)
- Router activation uses `apply_router_activation` on **all logits**, then gathers at selected experts

## ScatterMoE Token-Choice Shared (tc_shared)

Token-choice routing selects **top-k routed experts per token** while a shared expert
always processes every token. The shared output is added unweighted.

Key points:
- **n_experts**: `G × E + 1` (routed + 1 shared)
- **top_k**: `G - 1` (routed only)
- **No normalization** of gates (raw activated weights are used)
- `softmax_k` and `softmax_e_shared_out` are **not** supported
- `softmax_e` is applied over routed experts only (no shared anchor)

## Global Expert Choice (GEC) Implementation

### Architecture Overview

GEC uses a **composition pattern** with `ExpertEngine` + scatter backends:

```
GEC / GEC_shared (model wrappers)
    ↓ composes
ExpertEngine (routing + expert computation)
    ↓ returns (h_flat, indices, metrics)
Scatter Backend (aggregation with optional add_into fusion)
    ↓
Output
```

Key design: Engine returns **pre-scatter outputs**, allowing GEC_shared to fuse scatter with shared expert addition via `add_into` parameter.

**See `src/models/engines/README.md` for detailed engine architecture.**

### Routing Pipeline

GEC replaces dense FFN layers with a mixture of experts using **expert-choice** routing:

1. **Flatten inputs**: `x ∈ ℝ^(B×T×C)` → `x_flat ∈ ℝ^(N×C)` where `N = B·T`

2. **Compute router logits**: `torch.einsum('btc,ce->bte', x, router_w)` (BF16 autocast-friendly)

3. **Expert selection (top-k)**: Each expert selects exactly `k` tokens via `torch.topk(router_logits_flat.t(), k=k, dim=1)`
   - Returns expert-major indices: `(num_experts, k)`
   - Value of `k` computed via integer division (see CLAUDE.md for formulas)
   - EMA of expert cutoffs tracked for diagnostics

4. **Activate router weights**: Apply activation function (sigmoid/relu/softmax) to selected logits only

5. **Gather tokens**: `x_flat[indices.reshape(-1)].view(num_experts, k, C)`

6. **Expert MLPs**: Process with per-expert weights `(W1, W2)` and biases using batched GEMMs

7. **Normalize weights**: Scale router weights by normalization factor (see Normalization Modes)

8. **Scatter outputs**: Accumulate via `output.index_add_(0, indices, normalized_outputs)`
   - Normalization fused into weights before scatter for better performance
   - Allows torch.compile to fuse normalization with scatter operation

### Key Properties

- **No token exclusivity**: Tokens may be routed to zero, one, or multiple experts
- **Compute-matched**: Total activated parameters ≈ dense FFN (4 × n_embd)
- **Expert-choice**: Experts select tokens (not tokens selecting experts)
- **Top-k on raw logits**: Selection happens before activation, so activation doesn't affect routing

### Triton Kernels

Optimized gather/scatter kernels in `src/kernels/balanced.py`:
- Launch one program per expert-slot
- Stream contiguous hidden vectors without histogram metadata
- Scatter uses `tl.atomic_add` to mirror `index_add_`
- See `src/kernels/README.md` for details

## Normalization Modes

GEC variants support two normalization modes via `normalization_mode` config parameter.

### fanout (default)

**Normalize by count of experts that selected each token** (routing fanout).

```python
fanout = bincount(indices)  # how many experts selected each token
normalizer = fanout.clamp(min=1e-6)
```

For GEC_shared, the shared expert adds +1: `normalizer = fanout + 1`

**When to use**: Default mode. Works with sigmoid, relu, softmax_k activations.

### none

**No normalization** - use weights as-is from router activation.

For GEC_shared with non-softmax activations, the shared expert remains unweighted
(shared weight = 1.0).

**Required for**: `softmax_e` and `softmax_e_shared_out` activations (weights already normalized via softmax).

### Router Activation Functions

Configured via `router_activation`. All activations are applied BEFORE top-k selection.

**Implementation**: `src/models/router_utils.py`

| Activation | Description | Normalization Mode |
|------------|-------------|-------------------|
| `sigmoid` (default) | Bounded in (0,1), stable statistics | fanout |
| `relu` | Introduces sparsity, allows zero weights | fanout |
| `softmax_k` | Softmax across all tokens per expert (dim=0) | fanout |
| `softmax_e` | Softmax across experts per token, shared IN softmax | **none required** |
| `softmax_e_shared_out` | Same as softmax_e, but shared gets fixed 1/G weight | **none required** |

See `memory/design/gate_activation_normalization.md` for detailed explanation of softmax_e variants.

## Dtype Handling Under Autocast

All models use mixed precision training via `torch.autocast(dtype=torch.bfloat16)`.

### Expected Dtype Flow

- **Model parameters**: Stay in FP32 (not autocasted)
- **Input**: BF16 for intermediate layers (FP32 only for first layer after embeddings)
- **Matrix multiplications** (`torch.bmm`): Produce BF16 under autocast
- **Bias addition**: Manual `h + bias_fp32` promotes to FP32
- **Final output**: BF16 (important for next layer)

### Why Manual Bias Handling is Needed

GEC models use batched expert weights and cannot use `F.linear`:

```python
# DenseMLP (works correctly):
h = F.linear(x, weight, bias)  # Returns BF16 under autocast

# GEC models (need batched operations):
h = torch.bmm(x_batched, weight_batched)  # BF16
h = h + bias_batched                       # Promotes to FP32!
```

### Implementation Strategy

**Let FP32 computation happen, cast only at dtype boundaries:**

```python
# Intermediate computations stay in FP32 after bias addition
h = torch.bmm(x_permuted, self.weight1.transpose(1, 2))  # BF16
h = h + self.bias1.unsqueeze(1)                          # FP32 (promoted)
h = self.act(h)                                          # FP32
h = torch.bmm(h, self.weight2.transpose(1, 2))          # BF16 (autocasted)
h = h + self.bias2.unsqueeze(1)                          # FP32 (promoted)

# Normalize (FP32 precision)
h = h * weights / normalizer_h  # FP32

# Cast ONLY when accumulating into BF16 buffer
output.index_add_(0, indices, h.to(output.dtype))  # Cast at boundary
```

**Why this works:**
- Simpler code (fewer casts)
- Higher precision intermediate math (FP32)
- Final output still BF16 (matches autocast intent)
- torch.compile can fuse FP32 operations

**See `memory/design/dtype_handling.md` for detailed explanation.**

## Logits Softcapping

All models apply Gemma-style logits softcapping for training stability:

```python
softcap = 15.0
logits = softcap * torch.tanh(logits / softcap)
```

**Applied**: After `lm_head` projection, before computing loss or returning logits

**Purpose**: Prevents extreme logits that can destabilize training, especially with Muon optimizer

**Effect**: Soft bounds logits to roughly `[-15, 15]`, with gradients still flowing for large values

This is part of the nanochat training recipe and is always enabled.

## Routing Mode (Training vs Inference)

GEC models support two routing algorithms, configured via `routing_mode` during training:

### topk (Training)
- **Algorithm**: Global top-k selection per expert
- **Load balance**: Perfect (exactly k tokens per expert)
- **Causality**: Non-causal (requires full batch)
- **Backward pass**: ✅ Supported
- **Use case**: Training, batched inference benchmarks

### threshold (Inference)
- **Algorithm**: Per-token threshold check against learned cutoffs
- **Load balance**: Approximate (depends on cutoff EMA)
- **Causality**: Causal (token-by-token decisions)
- **Backward pass**: ❌ NOT supported (inference only)
- **Use case**: Autoregressive generation

### Routing Precedence

Eval always uses threshold routing; `routing_mode` only affects training:

```python
def forward(self, x, layer_idx=0):
    if not self.training:
        return self.forward_threshold(x, layer_idx)
    if self.routing_mode == 'threshold':
        return self.forward_threshold(x, layer_idx)
    return self.forward_topk(x, layer_idx)
```

### Training Override

Choose the training routing mode explicitly:

```python
# Train with topk (default)
config = ModelConfig(..., routing_mode='topk')

# Train with threshold (eval is always threshold)
config = ModelConfig(..., routing_mode='threshold')
```

### Runtime Mode Switching API

You can dynamically switch routing modes during training using `set_routing_mode()`:

```python
# Switch to threshold mode at step 1000
if step == 1000:
    model.set_routing_mode('threshold')

# Switch back to topk
model.set_routing_mode('topk')
```

**Method signature**:
```python
def set_routing_mode(self, mode: str):
    """Set routing mode for all MLP layers.

    Args:
        mode: 'topk' or 'threshold'
    """
```

**Use cases**:
- **Threshold warmup**: Start with topk routing, switch to threshold after EMA stabilizes
- **Benchmarking**: Compare topk vs threshold during training
- **Debugging**: Force specific mode during training (eval always threshold)

**Training loop integration**:
```python
# Start EMA updates earlier for better threshold eval calibration
if step >= config.training.ema_start_steps:
    ...

# Typical threshold training pattern
if step == config.training.threshold_warmup_steps:
    orig_model.set_routing_mode('threshold')
    print(f"Switched to threshold routing at step {step}")
```

### Implementation Notes

- Normalization applied to weights **before** multiplying with expert outputs
- Allows torch.compile to fuse normalization with scatter operation
- No separate normalization pass needed after scatter
- All modes compute the same metrics (fanout counts, etc.) for logging

## Trainable Threshold Routing with Capacity Constraints

### Overview

`GECSharedMLPCapacityThreshold` (`src/models/gec_shared/shared_capacity_threshold.py`) extends threshold routing to support training with optional expert capacity constraints. This addresses the train-test mismatch where training uses fixed top-k selection but inference uses variable threshold-based selection.

### Key Features

1. **Dual-path training**: Top-k (no_grad) for EMA updates + capacity-bounded threshold for computation
2. **Hard capacity bounds**: Each expert processes k ∈ [k_min, k_max] tokens during threshold routing
3. **Training compatible**: Full gradient flow through threshold routing path
4. **Configurable**: Set `expert_capacity_factor >= 0` to enable, `-1` to disable (pure threshold)

### Capacity Bounds

Given `k_target = ⌊n_tokens × (G-1) / (G×E)⌋` and capacity factor `α`:

```python
k_min = int(k_target × (1 - α))
k_max = int(k_target × (1 + α))
```

For each expert, threshold routing selects tokens as follows:

- Count tokens above threshold: `n_above = (router_logits[:, i] >= cutoff_ema[i]).sum()`
- If `n_above > k_max`: Clip to top k_max tokens by router logit
- If `n_above < k_min`: Expand to top k_min tokens (relax threshold)
- Otherwise: Use all tokens above threshold

### Configuration

```yaml
# configs/mlp/gec_shared_capacity.yaml
model:
  model_type: gec_shared_capacity
  expert_capacity_factor: 0.2  # ±20% bounds: [k×0.8, k×1.2]
                               # Set to -1 to disable (pure threshold)
```

### Usage

```python
# With capacity constraints
config = ModelConfig(
    model_type='gec_shared_capacity',
    expert_capacity_factor=0.2,  # Enabled
    routing_mode='threshold',
    threshold_warmup_steps=1000  # Switch from topk at step 1000
)

# Pure threshold (no capacity)
config = ModelConfig(
    model_type='gec_shared_capacity',
    expert_capacity_factor=-1.0,  # Disabled
    routing_mode='threshold',
    threshold_warmup_steps=1000
)
```

`ema_start_steps` is a `TrainingConfig` schedule parameter (not a `ModelConfig` field).

### Additional Metrics

When capacity is enabled (`expert_capacity_factor >= 0`), additional metrics are tracked:

**Global metrics:**
- `capacity_hit_rate`: Fraction of experts hitting capacity bounds (min or max)
- `capacity_overflow_rate`: Fraction hitting k_max (threshold too low)
- `capacity_underflow_rate`: Fraction hitting k_min (threshold too high)
- `raw_mean`: Average tokens per expert that pure threshold would select
- `raw_std`: Variance in pure threshold selection

**Per-expert metrics (representative layers):**
- `repr_L{i}_capacity_status`: Status per expert (0=hit_min, 1=within, 2=hit_max)
- `repr_L{i}_actual_k`: Actual tokens selected after capacity enforcement
- `repr_L{i}_raw_k`: Tokens pure threshold would select (for comparison)

### Behavior Summary

| Mode | Training | Inference | Gradients | Capacity |
|------|----------|-----------|-----------|----------|
| `GECSharedMLP` | topk | threshold | ✅ topk only | N/A |
| `GECSharedMLPTrainableThreshold` | threshold | threshold | ✅ dual-path | No bounds |
| `GECSharedMLPCapacityThreshold` | threshold | threshold | ✅ dual-path | Optional (α ≥ 0) |

**Note**: All three classes support the same `routing_mode` and threshold warmup mechanisms. Capacity constraints only affect threshold routing during training when `expert_capacity_factor >= 0`.

## Expert Choice (EC) with Configurable Routing Granularity

The EC model (`src/models/ec.py`) extends GEC by allowing configurable top-k selection granularity.

### Routing Granularities

Configured via `routing_chunk_seqs` parameter:

- **`routing_chunk_seqs = None`** (default): Global routing across entire micro-batch (standard GEC)
- **`routing_chunk_seqs = 1`**: Per-sequence routing (most local, each sequence independently)
- **`routing_chunk_seqs = N`**: Per-N-sequences routing (chunks of N sequences)

### Implementation Details

- Batch divided into `n_chunks = B // routing_chunk_seqs` chunks
- Each chunk has `chunk_size = routing_chunk_seqs × T` tokens
- Top-k selection: `k = chunk_size // E` per chunk (compute-matching within chunk)
- Global token indices adjusted with chunk offsets: `global_idx = chunk_idx × chunk_size + local_idx`
- Expert weights expanded across chunks for parallel batch processing
- Metrics track per-chunk behavior (cutoffs, usage, etc.)

### Trade-offs

- **Global routing** (routing_chunk_seqs=None): Better load balancing, cross-sequence expert sharing
- **Local routing** (routing_chunk_seqs=1): More fine-grained, sequence-specific expert selection
- **Intermediate** (routing_chunk_seqs=N): Balances global and local routing

## Expert Choice with Shared Expert (EC_shared)

The `ec_shared` model (`src/models/ec_shared.py`) combines:
- **Chunked routing** from EC
- **Shared expert architecture** from GEC_shared

### Implementation Strategy

Uses **inheritance** to minimize code duplication:

```python
class ECSharedMLP(GECSharedMLP):
    """Only overrides forward_topk() to add chunked routing."""

    def forward_topk(self, x, layer_idx=0):
        if self.routing_chunk_seqs is None:
            return super().forward_topk(x, layer_idx)  # Fallback to global routing
        # ... chunked routing implementation
```

### Benefits

- **Minimal code**: ~130 lines vs ~400+ if copied from gec_shared
- **Reuses all shared expert logic**: forward_threshold(), normalization, etc.
- **Clean fallback**: routing_chunk_seqs=None → identical to gec_shared
- **Easy maintenance**: Changes to gec_shared automatically propagate

### Configuration

```yaml
# configs/mlp/ec_shared.yaml
model:
  model_type: ec_shared
  routing_chunk_seqs: null  # null=global, 1=per-seq, 2/4/8/16=per-N-seqs
  # All other params same as gec_shared
```

### Usage

```bash
# Global routing (same as gec_shared)
python train.py mlp=ec_shared

# Per-sequence routing
python train.py mlp=ec_shared model.routing_chunk_seqs=1
```

**See `memory/design/ec_shared.md` for detailed design rationale.**

## File Organization

```
src/models/
├── README.md              # This file
├── model_base.py          # BaseGPT, ModelConfig, BaseMLP
├── router_utils.py        # apply_router_activation(), compute_fanout()
├── gec.py                 # Standard GEC (routed experts only)
├── gec_shared.py          # GEC with shared expert
├── ec.py                  # Expert Choice (legacy, uses RouterMixin)
├── ec_shared.py           # EC + shared expert (legacy)
├── scattermoe_tc.py       # ScatterMoE token-choice MLP (+ tc_shared)
├── engines/               # Expert computation engine
│   ├── README.md          # Engine architecture docs
│   ├── engine.py          # ExpertEngine (returns 6-tuple with shared_weights)
│   ├── parallel_experts_manual.py  # Expert Parallel version
│   ├── __init__.py        # Exports ExpertEngine
│   └── scatter.py         # ScatterMoE-style backend (legacy)
└── gec/                   # Legacy GEC variants (reference implementations)
    ├── reference.py       # Reference implementation
    ├── triton.py          # Triton kernel version
    └── triton1.py         # Triton kernel version (variant)

src/ops/
├── scatter_backends.py    # IndexAddScatter, IndexAddScatterFP32, CSRScatter, get_scatter()
├── csr.py                 # CSR autograd ops (CSRScatterOp, csr_scatter_sum)
├── scattermoe_ops.py      # ScatterMoE kernel wrappers
└── ...
```

**Note**: Router activation logic is in `router_utils.py`. EC/EC_shared use legacy `RouterMixin` pattern (not imported by default).

## Usage

See `configs/README.md` for configuration examples and CLI usage.

For core notation (G, E, k formulas), see `memory/design/notation.md`.
