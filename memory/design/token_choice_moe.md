# Token-Choice MoE Design (scattermoe_tc / tc)

## Purpose

Token-choice MoE baseline for comparing against expert-choice (GEC). Uses ScatterMoE Triton kernels for efficient computation.
`tc` is an alias for `scattermoe_tc`.

## Routing Comparison

| Aspect | Expert-Choice (GEC) | Token-Choice (scattermoe_tc / tc) |
|--------|---------------------|------------------------------|
| Selection unit | Each expert selects top-k tokens | Each token selects top-k experts |
| top_k formula | k = n_tokens // E (per expert) | top_k = G (per token) |
| Load balancing | Automatic (fixed k per expert) | Requires explicit control |
| Normalization | fanout/select_norm/all_norm | None (raw gates) |
| Compute variance | Per-expert consistency | Per-token consistency |

## Key Design Decisions

### 1. Kernel Strategy

Direct import from vendored scattermoe library:
- `scattermoe.scattermoe.parallel_experts.parallel_linear`
- `scattermoe.scattermoe.parallel_experts.flatten_sort_count`

No custom Triton kernels in this repo for token-choice.

### 2. No Normalization

Token-choice uses raw gate values directly. Unlike GEC where fanout varies per token (requiring normalization), token-choice has fixed fanout (top_k experts per token), so no normalization is needed.

### 3. Load Balancing Methods

Four methods supported via `load_balance_method` config:

- **none**: No load balancing (may cause expert collapse)
- **aux**: Switch/GShard auxiliary loss: `aux_loss = sum((E × f) × p)` where f=fraction tokens per expert, p=mean activated router weight (`all_weights` from `apply_router_activation`)
- **aux_error**: Error-centered aux loss: `aux_loss = sum((E × f - 1) × p)` (targets uniform expert usage)
- **deepseek**: Loss-free bias update - learnable per-expert bias adjusted based on EMA expert counts

### 4. top_k Derivation

`top_k = n_experts // expansion = granularity`

This matches GEC compute (same number of expert-token computations per forward pass).

### 5. Router Activation

Reuses `apply_router_activation()` from `router_utils.py`:
- `softmax_k` is **not supported** (token-choice semantics incompatible)
- Default: `sigmoid`
- Activation applied to all logits, then weights gathered at selected indices

### 6. Parameter Layout

Packed 2D parameters for DDP compatibility with DistMuon:
- `expert_weight1`: (n_experts * expert_dim, n_embd)
- `expert_weight2`: (n_experts * n_embd, expert_dim)

Views created at runtime for ScatterMoE kernels.

## Implementation Files

- **Model**: `src/models/scattermoe_tc.py`
- **Config**: `configs/mlp/scattermoe_tc.yaml` (alias: `configs/mlp/tc.yaml`)
- **Test**: `test/test_scattermoe_tc.py`

## See Also

- Implementation details: `src/models/README.md`
- Original plan: `memory/archive/completed/scattermoe_mlp_integration.md`
