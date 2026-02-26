# MoE/GEC Notation (Following "Scaling Laws for Fine-Grained Mixture of Experts")

## Core Parameters

- **G (granularity)**: Ratio of FFN dimension to expert dimension: `G = d_ff / d_expert` where `d_ff = 4 × n_embd`
  - **Constraint**: G must be a power of 2 (ensures expert_dim is an integer)
- **E (expansion)**: Total MoE parameters relative to dense FFN parameters
- **Derived values**:
  - `n_experts = G × E` (for regular GEC)
  - `n_experts = (G × E) + 1` (for GEC shared: routed + 1 shared)
  - `expert_dim = d_ff / G = (4 × n_embd) / G` (dimension of each expert)

## Token Selection (Compute-Matching)

Token selection uses **integer division** to avoid float errors:

- **Regular GEC**: `k = n_tokens // E`
  - Each expert selects k tokens
  - Total activated: E × (n_tokens // E) × expert_dim ≈ 4 × n_embd ✓

- **GEC shared**: `k = n_tokens × (G-1) // (G × E)`
  - Shared expert processes all tokens, contributes (G-1)/G of dense compute
  - Need (G-1) routed experts active per token for compute-matching
  - Total activated: shared_dim + (G-1) × expert_dim ≈ 4 × n_embd ✓

## Unified Notation

**Important**: E always refers to **routed expert expansion** for both GEC and GEC shared:

- **GEC**: n_experts = G × E (all are routed experts)
  - True parameter expansion = E
- **GEC shared**: n_experts = (G × E) + 1 (G × E routed + 1 shared)
  - True parameter expansion = E + 1/G (e.g., E=8, G=2 → 8.5x total expansion)

This means:
- GEC with E=8 → 16 routed experts (8x expansion)
- GEC shared with E=8 → 16 routed + 1 shared = 17 total experts (8.5x expansion)
- Both have the same routed capacity (E=8), but GEC shared has +0.5x from the shared expert

**Note**: This notation prioritizes **unified routed capacity** over exact parameter expansion. For GEC shared, true expansion is slightly higher (E + 1/G) due to the shared expert.

## Defaults (E=4)

- `granularity = 2` → expert_dim = 2 × n_embd
- `expansion = 4` → n_experts = 8 (regular GEC) or 9 (GEC shared)
- Token selection: `k = n_tokens // 4` (automatic, no config needed)

## Validation Rules

- **G must be power of 2** (enforced by ModelConfig)
- **GEC shared requires G ≥ 2** (shared expert needs at least half of dense compute)
- **Valid model_type values**: `["dense", "gec", "gec_shared", "ec", "scattermoe_tc"]`

## Implementation Status

**Training configs** (`configs/`):
- ✅ Uses G/E notation exclusively
- ✅ Automatic num_experts computation: `n_experts = G × E` (GEC) or `(G × E) + 1` (GEC shared)
- ✅ No density or selection_rate parameters needed in configs
- ✅ Token selection computed via integer division at runtime

**Benchmarks** (`benchmark/mlp/`):
- ✅ Uses G/E notation via CLI: `-G 2 -E 8`
- ✅ Automatic num_experts computation in all GEC benchmarks (forward, autograd, threshold, comparison)
- ✅ Density derived internally as `1/E` when needed for ModelConfig compatibility
- ✅ FLOPs calculations use `k = n_tokens // E` directly
- ✅ All documentation updated (READMEs, help text, examples)

**Migration completed:** October 2025
- Removed `--experts` flag from GEC benchmarks
- Removed `density` and `selection_rate` from BenchmarkConfig and model config dictionaries
- Updated all examples in project documentation to use G/E notation

**Consistency achieved:**
```bash
# Training
python train.py mlp=gec model_size=tiny  # Uses G=2, E=8 from config

# Benchmarking (now consistent!)
python -m benchmark.mlp.gec -G 2 -E 8    # Same G/E parameters
```

## Token-Choice Notation (scattermoe_tc)

For token-choice MoE, top_k represents **experts per token** (inverse of GEC):
- `top_k = n_experts // expansion = granularity`
- Each token selects exactly `top_k` experts
- No normalization needed (fixed fanout)

See `memory/design/token_choice_moe.md` for full design.

## See Also

- **Config examples**: `configs/README.md`
- **Implementation details**: `src/models/README.md`
- **Normalization modes**: `src/models/README.md`
- **Token-choice design**: `memory/design/token_choice_moe.md`
