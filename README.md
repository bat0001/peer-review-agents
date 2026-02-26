# GEC: Global Expert Choice Training Framework

Clean implementation of sparse Mixture-of-Experts (MoE) architectures with Global Expert Choice (GEC) routing.

## What is GEC?

**GEC (Global Expert Choice)** is a sparse MoE architecture where experts select top-k tokens from the entire batch. Each expert processes exactly k = ⌊BT/E⌋ tokens, achieving:
- Perfect load balancing
- Dynamic per-token computation (0 to GE experts can activate per token)
- Causal inference via EMA-tracked cutoffs

**Key differences from Expert Choice (EC):**
- GEC selects top-k tokens globally (entire batch) vs EC per-sequence
- Lower variance in router cutoffs
- Enables causal inference without future tokens

See `memory/design/notation.md` for detailed formulas and `src/models/README.md` for implementation details.

## nanochat Integration

This codebase integrates proven training techniques from [nanochat](https://github.com/KellerJordan/nanochat) while preserving GEC's unique routing contributions:

**Adopted from nanochat:**
- **Muon Optimizer**: Newton-Schulz orthogonalized momentum for 2D matrices (35% speedup)
- **Hybrid Optimizer**: AdamW for embeddings (lr=0.2), Muon for matrices (lr=0.02)
- **RoPE**: Rotary position embeddings replacing learned positional encodings
- **QK Normalization**: Functional normalization for attention stability
- **ReLU² Activation**: Faster training than GELU
- **No Bias**: All linear layers bias-free for parameter efficiency
- **Untied Embeddings**: Separate wte and lm_head weights
- **Constant LR Schedule**: No warmup, constant LR with linear warmdown (last 20%)
- **ZeRO-2 Strategy**: Manual gradient sync, no DDP wrapper

**Preserved from nano_gec:**
- GEC routing logic and all MLP variants (dense, gec, gec_shared, ec)
- Triton kernels for efficient gather/scatter operations
- Hydra configuration system
- Comprehensive metrics and visualization

See `memory/archive/deprecated/IMPLEMENTATION.md` for historical integration details.

## Setup

```bash
# Create environment and install dependencies
conda create -n nanochat python=3.12 -y
conda activate nanochat

# Option 1: Install from setup.py (editable install)
pip install -e .

# Option 2: Install from requirements.txt
pip install -r requirements.txt

# Optional: login to wandb for experiment tracking
wandb login
```

**Note**: If you get `ModuleNotFoundError`, make sure you ran one of the pip install commands above.

## Quick Start

```bash
# Download parquet shards (FineWeb-Edu 100B)
python -m src.data.nanochat_dataset --num-files 1 --data-dir /data2/.cache/nanochat/base_data

# Train with Hydra config composition
python train.py                          # Default: tiny gec_shared, debug mode
python train.py model_size=medium mlp=dense experiment=full_run
python train.py model_size=tiny mlp=gec_shared
python train.py --config-name=presets/gec_shared_tiny

# CORE eval from a checkpoint
python -m script.eval_core eval.core_checkpoint_path=/path/to/checkpoint.pt

# For more details, see configs/README.md
```

## Debug Training

For quick testing and debugging, use the debug experiment:

```bash
# Run debug training (no compile, no wandb, small batch)
python train.py +experiment=debug

# Test specific model types
python train.py model_size=micro mlp=dense +experiment=debug
python train.py model_size=tiny mlp=gec_shared +experiment=debug
python train.py +experiment=debug training.max_steps=50
```

The debug experiment:
- Disables compilation for faster startup
- Disables wandb for quick iteration
- Small batch size (65536 tokens)
- Runs for only 100 steps
- Perfect for testing code changes

## Configuration System

This project uses **Hydra** for composable configuration. Mix and match config groups:

| Group | Options | Description |
|-------|---------|-------------|
| `model_size/` | micro, tiny, small, medium, large | Model scale (n_embd, n_layer, n_head) |
| `mlp/` | dense, gec, gec_shared, ec | MLP architecture type |
| `experiment/` | debug, ablation_router, full_run | Experimental settings |
| `training/` | quick, standard, long | Training duration and batch config |
| `presets/` | gec_shared_tiny, dense_medium | Ready-to-run combinations |

**Examples:**
```bash
# Compose from groups
python train.py model_size=tiny mlp=gec_shared +experiment=debug

# Override specific values
python train.py model.router_activation=relu training.learning_rate=0.001

# Run ablation sweeps (4 experiments)
python train.py --multirun experiment=ablation_router \
  model.router_activation=sigmoid,relu,softmax_k,softmax_e
```

See **`configs/README.md`** for complete documentation.

### Legacy Configs

Old monolithic configs have been moved to `configs/legacy_configs/` and are deprecated.

### Configuration Examples

**Dense baseline (124M params):**
```yaml
model:
  model_type: "dense"
  n_embd: 768
  n_layer: 12
  n_head: 12
```

**GEC (16 experts, 2 active per token avg):**
```yaml
model:
  model_type: "gec"
  granularity: 2      # G: controls expert_dim = dff/G
  expansion: 8        # E: total params / dense
  # Results: 16 experts (G×E), expert_dim=1536
  # Token selection: k = BT/8 (compute-matching)
```

**GEC + Shared (1 shared + 16 routed experts):**
```yaml
model:
  model_type: "gec_shared"
  granularity: 2
  expansion: 8
  shared_expert_dim: 1536  # Shared expert processes all tokens
  # Results: 1 shared + ~1 routed expert per token
```

**Optimizer (nanochat hybrid):**
```yaml
optimizer:
  embedding_lr: 0.2        # wte (50x baseline)
  matrix_lr: 0.02          # Muon for transformer blocks (5x baseline)
  unembedding_lr: 0.004    # lm_head (baseline)
  muon_momentum: 0.95      # Muon momentum
  warmup_ratio: 0.0        # No warmup
  warmdown_ratio: 0.2      # Linear decay last 20%
```

## Project Structure

```
gec/
├── train.py                 # Main training script (direct loop, nanochat style)
├── input.txt               # Sample text for debug training
├── configs/                # Configuration files (Hydra)
│   ├── config.yaml        # Base configuration
│   ├── model_size/        # Model scales (micro, tiny, medium, large)
│   ├── mlp/               # MLP types (dense, gec, gec_shared, ec)
│   ├── optimizer/         # Optimizer configs (nanochat hybrid)
│   ├── training/          # Training duration configs
│   └── experiment/        # Experiment presets (debug, full_run)
├── src/
│   ├── models/            # Model implementations
│   │   ├── model_base.py # Base GPT with RoPE, QK norm, ReLU²
│   │   ├── gec.py        # GEC MLP (routed experts only)
│   │   ├── gec_shared.py # GEC+Shared MLP (routed + shared expert)
│   │   ├── ec_shared.py  # EC+Shared (chunked routing)
│   │   ├── scattermoe_tc.py # Token-choice baseline (ScatterMoE kernels)
│   │   └── engines/      # ExpertEngine and ParallelExperts
│   ├── optimizers/        # Hybrid optimizer system (nanochat)
│   │   ├── muon.py       # Muon optimizer
│   │   ├── adamw_dist.py # Distributed AdamW (ZeRO-2)
│   │   └── factory.py    # Hybrid optimizer factory
│   ├── kernels/          # Triton kernels for efficient routing
│   ├── utils/            # Metrics, logging, visualization, distributed
│   ├── config.py         # Configuration system (Hydra)
│   └── data_loader.py    # Simplified streaming data loader
├── benchmark/            # Performance benchmarks (model testing)
├── test/                 # Integration tests
└── memory/              # Design docs and plans
```

## Training

### Single GPU

```bash
python train.py --config configs/gec.yaml
```

### Multi-GPU (Distributed)

```bash
# 2 GPUs
torchrun --nproc_per_node=2 train.py model_size=medium mlp=gec_shared

# 8 GPUs
torchrun --nproc_per_node=8 train.py model_size=large mlp=gec_shared experiment=full_run
```

### Hydra Overrides

```bash
# Override batch size
python train.py training.total_batch_size=262144

# Override learning rate
python train.py training.learning_rate=3e-4

# Short training run
python train.py training.max_steps=1000

# Disable wandb
python train.py logging.use_wandb=false

# Combine overrides
python train.py model_size=medium mlp=dense training.learning_rate=0.001 \
  experiment.name="my-experiment"

# Override optimizer settings
python train.py optimizer.matrix_lr=0.03 optimizer.embedding_lr=0.3

# Switch optimizer config
python train.py optimizer=custom_optimizer
```

## Evaluation & Visualization

The framework includes automatic routing behavior visualization during evaluation:

- **JSON logs** (every eval_interval): Lightweight statistics
  - Expert activation histograms
  - Router weight percentiles

- **Plots** (every plot_interval): Detailed visualizations
  - Router weight CDF
  - Loss distribution by expert count
  - Expert cutoff distributions
  - Token entropy vs expert activation

Enable/disable in config:
```yaml
training:
  enable_visualizations: true
  eval_interval: 500        # Run eval every 500 steps
  plot_interval: 5000       # Generate plots every 5000 steps
```

Output structure:
```
outputs/{experiment_name}/
├── eval_logs/
│   ├── expert_counts.json
│   └── weight_percentiles.json
└── visualizations/
    └── step_5000/
        ├── weight_cdf/
        ├── loss_by_experts/
        ├── cutoff_vs_loss/
        └── entropy_vs_experts/
```

## Testing

```bash
# Run visualization tests
python test/test_visualizations.py

# Run metrics logging tests
python test/test_metrics_logging.py

# Run model benchmarks (in benchmark/)
python -m benchmark.mlp --mode all --tokens 2048 --hidden 256 -G 2 -E 4
```

See `test/README.md` and `benchmark/README.md` for details.

## Key Features

### 1. Unified Model Architecture
- Single base model (`BaseGPT`) with plugin system for different MLP variants
- Consistent forward pass interface across all models
- Clean separation between model architecture and training logic
- Self-contained utils (metrics, logging, visualization)

### 2. Efficient Routing
- Custom Triton kernels for gather/scatter operations
- Multiple routing modes: sigmoid, relu, softmax
- Multiple normalization strategies: fanout, select_norm, all_norm
- EMA-tracked cutoffs for causal inference

### 3. Comprehensive Metrics
- Detailed routing statistics (expert usage, token fanout, cutoffs)
- Hierarchical organization for wandb
- Representative layer tracking with temporal windows
- Automatic visualization during evaluation

### 4. Flexible Configuration
- Hydra-based composable configs (mix model size + MLP type + experiment)
- Structured configs with dataclass validation
- Multi-run support for ablation sweeps
- Paper notation (G, E) for expert configuration

### 5. Modular Design
- Clear module boundaries
- No circular dependencies
- Each module has single responsibility
- Easy to extend and test

## Configuration Options

### Model Configuration
- `model_type`: "dense", "gec", "gec_shared", or "ec"
- `granularity` (G): Controls expert_dim = dff/G (must be power of 2)
- `expansion` (E): Total params / dense params
- `n_experts`: G × E (computed automatically)
- `router_activation`: "sigmoid", "relu", "softmax_k", "softmax_e"
- `normalization_mode`: "fanout", "select_norm", "all_norm"

### Training Configuration
- `total_batch_size`: Total batch size in tokens
- `per_device_batch_size`: Samples per device
- `sequence_length`: Tokens per sample
- `learning_rate`: Base learning rate
- `lr_schedule`: "cosine", "linear", or "constant"
- `max_steps` or `max_epochs`: Training duration
- `compile_model`: Use torch.compile (enabled by default)

### Data Configuration
- `data_path`: Path to data files
- `use_sharded`: Use pre-sharded data (true) or lazy loading (false)

### Logging Configuration
- `use_wandb`: Enable Weights & Biases logging
- `wandb_project`: W&B project name
- `log_interval`: Steps between logging
- `eval_interval`: Steps between evaluation
- `save_interval`: Steps between checkpoints

## Design Principles

1. **Minimal models/**: Model implementations focus on forward/backward passes only
2. **Self-contained utils/**: All metrics, logging, visualization in utils/
3. **Testing philosophy**: Model testing via benchmark/, everything else in test/
4. **Let it crash**: No error handling except in utils/ for data preparation
5. **Clean abstractions**: Trainer doesn't know about model-specific details

## Extending the Framework

### Adding a New Model Variant

1. Create a new MLP class in `src/models/`:
```python
class MyCustomMLP(BaseMLP):
    def forward(self, x, layer_idx=0):
        # Your implementation
        return output, metrics
```

2. Update `_get_mlp_class` in `model_base.py`.

3. Create a configuration file.

### Adding New Metrics

Return additional metrics from your model's forward pass - they will automatically be tracked and logged.

### Custom Visualizations

Extend `EvalVisualizer` in `src/utils/visualizer.py` to add new plot types.

## Citation

If you use this code, please cite the relevant papers:

```bibtex
@article{clark2022unified,
  title={Unified scaling laws for routed language models},
  author={Clark, Aidan and others},
  journal={ICML},
  year={2022}
}

@article{zhou2022mixture,
  title={Mixture-of-experts with expert choice routing},
  author={Zhou, Yanqi and others},
  journal={NeurIPS},
  year={2022}
}
```

## License

MIT License - see LICENSE file for details.
# Global-Expert-Choice
