# Configuration Guide

This project uses [Hydra](https://hydra.cc/) for composable, flexible configuration management.

## Directory Structure (Hydra)

```
configs/
├── config.yaml              # Base configuration
├── analysis/                 # Analysis scripts (expert specialization, etc.)
├── model_size/              # Model scale (tiny/medium/large)
├── mlp/                     # MLP type (dense/gec/gec_shared/ec/scattermoe_tc/tc/tc_shared)
├── experiment/              # Experiment settings (debug/ablation/full_run)
├── training/                # Training regime (quick/standard/long)
├── eval/                    # CORE eval settings
└── presets/                 # Ready-to-run combinations
```

## Quick Start

```bash
# Use defaults (tiny gec_shared)
python train.py

# Add experiment config (use + prefix since experiment not in defaults)
python train.py +experiment=debug
python train.py +experiment=full_run

# Override config groups (model_size, mlp, training are in defaults)
python train.py model_size=medium mlp=dense

# Override specific values
python train.py model.router_activation=relu training.learning_rate=0.001

# Use a preset
python train.py --config-name=presets/gec_shared_tiny

# Run ablation sweep
python train.py --multirun \
  +experiment=ablation_router \
  model.router_activation=sigmoid,relu,softmax_k,softmax_e
```

**Note**: The `experiment/` config group is NOT in `config.yaml` defaults, so you must use `+experiment=...` to add it. Other groups (`model_size`, `mlp`, `training`, `optimizer`) are in defaults and don't need the `+` prefix.

## Hydra Config Groups

### data (base config)
Data settings live in `configs/config.yaml` (not a separate group).

- `data_path`: parquet shard directory (default `/data2/.cache/nanochat/base_data`)
- `tokenizer_dir`: RustBPE tokenizer directory (default `/data2/.cache/nanochat/tokenizer`)
- `tokenizer_threads`: encoder thread count
- `tokenizer_batch_size`: batch size for tokenizer.encode
- `nanochat_base_dir`: base cache dir for nanochat artifacts

### model_size/
Defines model architecture scale (n_embd, n_layer, n_head).

- **micro**: 256 embd, 4 layers (~7M params, testing only)
- **tiny**: 512 embd, 8 layers (~55M params, GPT-2 Tiny)
- **small**: 768 embd, 12 layers (~117M params, GPT-2 Small)
- **medium**: 1024 embd, 24 layers (~345M params, GPT-2 Medium)
- **large**: 1280 embd, 36 layers (~774M params, GPT-2 Large)
- **d4** ... **d34**: nanochat depth configs (n_embd = depth * 64, head_dim = 128)

### mlp/
Defines MLP architecture type and expert configuration.

- **dense**: Standard FFN (no MoE)
- **gec**: GEC without shared expert (G=2, E=8, 16 experts)
- **gec_shared**: GEC with shared expert (G=2, E=8, 17 experts)
- **ec**: Expert Choice with configurable routing granularity
- **scattermoe_tc**: ScatterMoE-backed token-choice MoE (top-k experts per token)
- **tc**: Alias for scattermoe_tc
- **tc_shared**: ScatterMoE-backed token-choice MoE with a shared expert

All MoE types default to:
- `granularity=2` (G=2)
- `expansion=8` (E=8)
- `router_activation=sigmoid`
- `normalization_mode=fanout`
- `first_layer_dense=true` (L0 uses dense MLP to avoid routing instability)

### experiment/
Controls experimental settings (wandb, eval intervals, visualizations).

- **debug**: 100 steps, no wandb, no compilation, small batch (65536 tokens)
- **threshold_training**: Threshold routing warmup experiment

### training/
Defines training duration and batch configuration.

- **standard**: 10B tokens, 524288 total_batch_size

Defaults align with nanochat:
- `eval_interval=250`
- `eval_tokens=20*524288`

### eval/
Defines CORE evaluation defaults.

- `core_metric_every`: steps between CORE evals during training
- `core_metric_max_per_task`: cap per task for faster debug evals
- `core_bundle_url`: zip URL for CORE eval data
- `core_bundle_dir`: extracted bundle path
- `core_checkpoint_path`: checkpoint for `eval_core.py`

### analysis/
Analysis configuration groups used by standalone scripts.

- `expert_specialization.yaml`: GSM8K + HumanEval routing analysis (prefill-only)

### presets/
Ready-to-run preset combinations. These are self-contained configs that include all required base fields.

- **gec_shared_tiny**: GEC-shared tiny for ablation studies
- **dense_medium**: Dense medium baseline

**Note**: Presets use `@package _global_` to ensure all fields are placed at the top level. They include all required base config fields (`output_dir`, `data`, `model.vocab_size`, etc.) to work with `--config-name=presets/<name>`.

## Core Model Parameters

### Granularity (G) and Expansion (E)

From `memory/design/notation.md`:
- **G (granularity)**: `G = d_ff / d_expert` - Must be power of 2
- **E (expansion)**: Total MoE parameters relative to dense FFN
- **Derived**: `n_experts = G × E` (regular GEC) or `n_experts = (G × E) + 1` (GEC shared)

### Token Selection (k)

Automatically computed via integer division:
- **GEC**: `k = n_tokens // E`
- **GEC shared**: `k = n_tokens × (G-1) // (G × E)`

No need to specify `selection_rate` in configs!

## Configuration Design Principles

### Training Schedule vs Model Architecture

**Key principle**: Distinguish between model architecture decisions (ModelConfig) and training schedule decisions (TrainingConfig).

**ModelConfig**: Defines model structure that persists in checkpoints
- Model type, layer count, hidden dimensions
- Expert configuration (G, E)
- Router/normalization settings

**TrainingConfig**: Controls training behavior without changing model structure
- Learning rate, batch size, warmup steps
- Checkpoint intervals, evaluation frequency
- **ema_start_steps**: When cutoff EMA updates begin
- **threshold_warmup_steps**: When to switch from topk to threshold routing

**Why this matters**:
- Same model checkpoint can be trained with different schedules
- Model architecture is independent of training recipe
- Checkpoints are reusable across different training configurations

**EP checkpoint note**:
- EP runs should save contiguous expert indices (`0..n_routed_experts-1`) per layer.
- If you see gapped indices in older EP checkpoints, repair them with
  `script/archived/fix_ep_checkpoint_indices.py` and use the `*_fixed.pt` output.

**Example**: warmup gates belong in TrainingConfig, not ModelConfig, because:
- They control *when* training behavior changes (schedule)
- Same model works with different gate schedules (e.g., `ema_start_steps=200`, `threshold_warmup_steps=1000`)
- Checkpoint doesn't depend on which warmup schedule was used

## Configuration Examples

### Standard GEC (E=4, default)

```yaml
model:
  model_type: "gec"
  granularity: 2          # G=2: expert_dim = 2 × n_embd
  expansion: 4            # E=4: n_experts = 8
  # k = n_tokens // 4 (computed automatically)
```

### Higher Capacity GEC (E=8)

```yaml
model:
  model_type: "gec"
  granularity: 2          # G=2: expert_dim = 2 × n_embd
  expansion: 8            # E=8: n_experts = 16
  # k = n_tokens // 8 (computed automatically)
```

### GEC Shared (E=8 routed experts)

```yaml
model:
  model_type: "gec_shared"
  granularity: 2          # G=2
  expansion: 8            # E=8: 16 routed + 1 shared = 17 total experts
  # True expansion: 8.5x (8x routed + 0.5x shared)
  # k = n_tokens × 1 // 16 (computed automatically)
```

### Router Configuration

```yaml
model:
  model_type: "gec"
  granularity: 2
  expansion: 8
  router_activation: "sigmoid"     # sigmoid, relu, softmax_k, softmax_e
  normalization_mode: "fanout"     # none, fanout, select_norm, all_norm
  routing_mode: "topk"             # topk (default) or threshold
```

**Router activation options:**
- `sigmoid` (default) - Bounded in (0,1), stable gate statistics
- `relu` - Introduces sparsity, allows zero weights
- `softmax_k` - Softmax over k selected tokens within each expert
- `softmax_e` - Softmax over experts for each token (use with normalization_mode='none')
Note: `softmax_k` is not supported for token-choice (`scattermoe_tc`, `tc`, `tc_shared`).
Note: `softmax_e_shared_out` is not supported for `tc_shared`.

**Normalization mode options:**
- `none` - No normalization (raw expert outputs summed)
- `fanout` (default) - Normalize by expert count per token
- `select_norm` - Normalize by sum of selected router weights
- `all_norm` - Normalize by sum of ALL router weights
Note: `scattermoe_tc`/`tc` and `tc_shared` ignore normalization_mode (raw gates only).

**Routing mode options (training only):**
- `topk` (default) - Use topk routing during training (perfect load balance)
- `threshold` - Train with threshold routing (eval is always threshold)

See `src/models/README.md` for detailed explanations.

### EC Model (Configurable Routing Granularity)

```yaml
model:
  model_type: "ec"
  granularity: 2          # G=2: expert_dim = 2 × n_embd
  expansion: 8            # E=8: n_experts = 16
  routing_chunk_seqs: 4   # Route per 4 sequences
```

**Routing granularity options:**
- `routing_chunk_seqs: null` - Global routing (standard GEC)
- `routing_chunk_seqs: 1` - Per-sequence routing (most local)
- `routing_chunk_seqs: N` - Per-N-sequences routing

### ScatterMoE Token-Choice (scattermoe_tc / tc)

```yaml
model:
  model_type: "scattermoe_tc"
  granularity: 2          # G=2: expert_dim = 2 × n_embd
  expansion: 8            # E=8: n_experts = 16
  # top_k = G (derived)
  router_activation: "sigmoid"
  load_balance_method: "none"  # none, aux, aux_error, deepseek
```

### ScatterMoE Token-Choice Shared (tc_shared)

```yaml
model:
  model_type: "tc_shared"
  granularity: 2          # G=2: expert_dim = 2 × n_embd
  expansion: 8            # E=8: n_experts = 16 + 1 shared
  # top_k = G - 1 (derived)
  router_activation: "sigmoid"  # sigmoid, relu, softmax_e
  load_balance_method: "none"  # none, aux, aux_error, deepseek
```

## CLI Overrides

Override config parameters from command line:

```bash
# Override model type (useful for debug_moe.yaml)
python train.py --config configs/debug_moe.yaml --model_type ec

# Override routing parameters
python train.py --config configs/ec.yaml --routing_chunk_seqs 4
python train.py --config configs/debug_moe.yaml --router_activation relu
python train.py --config configs/debug_moe.yaml --normalization_mode select_norm

# Override training parameters
python train.py --config configs/gec.yaml --max_steps 1000
python train.py --config configs/debug_dense.yaml --learning_rate 1e-3

# Multiple overrides
python train.py --config configs/debug_moe.yaml \
  --model_type gec \
  --router_activation relu \
  --normalization_mode select_norm \
  --max_steps 50
```

## Experiment Scripts

### EC Routing Granularity Ablations

Script: `script/run_ec_experiments.sh`

Runs systematic ablations:
- Fixed: seq_length=1024, per_device_batch_size=16, total_batch_size=524288
- Variable: routing_chunk_seqs=[1, 2, 4, 8, 16]
- Uses GPUs 1-8 (CUDA_VISIBLE_DEVICES=1,2,3,4,5,6,7,8)
- Logs to wandb project: "gec-routing-granularity"

```bash
# Run EC experiments
bash script/run_ec_experiments.sh
```

## Available Config Files

### Debug Configs
| File | Model Type | Description |
|------|------------|-------------|
| `debug_dense.yaml` | dense | Debug dense models (128 dim, 2 layers) |
| `debug_moe.yaml` | gec/gec_shared/ec | Debug MoE models (override with --model_type) |

### Production Configs
| File | Model Type | Description |
|------|------------|-------------|
| `dense.yaml` | dense | GPT-2 small baseline (117M params) |
| `dense_medium.yaml` | dense | GPT-2 medium baseline (355M params) |
| `gec.yaml` | gec | Pure GEC: 16 routed experts (16a2) |
| `gec_shared.yaml` | gec_shared | GEC + shared: 16 routed + 1 shared (16a1+1) |
| `gec_shared_medium.yaml` | gec_shared | Medium GEC + shared: 8 routed + 1 shared (8a1+1) |
| `ec.yaml` | ec | Expert Choice with configurable routing |


## Common Model Architectures

| Model Size | Params | vocab_size | n_embd | n_layer | n_head | head_dim | ffn_dim | ffn_ratio |
|------------|--------|------------|--------|---------|--------|----------|---------|-----------|
| **GPT-2 tiny** | ~55M | 50257 | 512 | 8 | 8 | 64 | 2048 | 4.0 |
| GPT-2 small | 117M | 50257 | 768 | 12 | 12 | 64 | 3072 | 4.0 |
| GPT-2 medium | 345M | 50257 | 1024 | 24 | 16 | 64 | 4096 | 4.0 |
| GPT-2 large | 762M | 50257 | 1280 | 36 | 20 | 64 | 5120 | 4.0 |
| GPT-2 xl | 1.5B | 50257 | 1600 | 48 | 25 | 64 | 6400 | 4.0 |

**Notes:** GPT-2 tiny is a custom config for testing. Context length (`training.sequence_length`) defaults to 1024. All models use head_dim=64 and ffn_ratio=4.0.


## Validation Rules

ModelConfig enforces:
- **G must be power of 2** (ensures expert_dim is integer)
- **GEC shared requires G ≥ 2** (shared expert needs at least half of dense compute)
- **Valid model_type values**: `["dense", "gec", "gec_shared", "ec"]`

## Legacy Parameters

- **`density`** - Deprecated, use `expansion` instead (will show warning)
- **`selection_rate`** - No longer needed, k computed automatically via integer division

## See Also

- **Core notation and formulas**: `memory/design/notation.md`
- **Model implementation details**: `src/models/README.md`
- **Kernel implementation**: `src/kernels/README.md`
