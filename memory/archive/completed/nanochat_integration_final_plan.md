# nanochat Integration Plan - Final Design

**Status**: ✅ COMPLETED (October 19, 2025)
**Implementation**: See IMPLEMENTATION.md and TESTING_PLAN.md in project root
**Key Files**: src/optimizers/, src/models/model_base.py, train.py

All 8 testing phases passed successfully. Integration complete.

---

**Original Plan Details:**

**Date**: October 19, 2025
**Goal**: Incorporate nanochat's training techniques into nano_gec with strict adherence to nanochat architecture

---

## Executive Summary

This plan integrates nanochat's proven training techniques into nano_gec while:
- **Following nanochat architecture strictly** (no backward compatibility, no config options for arch features)
- **Preserving nano_gec's MoE/GEC contributions** (routing logic, Triton kernels)
- **Keeping Hydra config system** (superior for research)
- **Adopting ZeRO-2 distributed strategy** (no DDP wrapper, manual sync via optimizers)
- **Simplifying data loading** (nanochat's streaming approach)

**Key Performance Expected**: 35% speedup from Muon optimizer + faster convergence from constant LR schedule.

---

## Part 0: Backward Compatibility - NONE

**Core Principle**: Ignore all backward compatibility. Clean break for highest code quality.

**What breaks (retrain from scratch)**:
- ❌ Model checkpoints (RoPE ≠ wpe, untied embeddings, no bias, different param names)
- ❌ Optimizer states (dual optimizers, different state structure)
- ⚠️ Configs (add `optimizer: nanochat`, update data loader settings)
- ❌ Training code (`Trainer` class → direct loop)
- ✅ Benchmarks (MLP interfaces unchanged, fix imports only)

**Rationale**: Early research stage. Complexity of compatibility > benefit of loading old checkpoints. Retrain is faster with Muon anyway.

**Safety**: Old code in git history. Can revert if needed.

---

## Part 1: Design Decisions

### 1.1 Trainer: Direct Loop vs Class

**Decision**: Adopt nanochat's direct training loop (no Trainer class)

**Rationale**:
Both approaches are ~90% similar in complexity, but direct loop has slight advantages for research code:

| Aspect | Direct Loop (nanochat) | Trainer Class (nano_gec) |
|--------|----------------------|------------------------|
| **Lines of code** | ~200 in train.py | ~200 split across methods |
| **Visibility** | Entire flow in one place | Split across methods |
| **Hackability** | Easy to add inline experiments | Need to modify methods |
| **Indirection** | Zero (everything visible) | Methods hide some complexity |
| **Proven** | SOTA speedruns use this | Common in frameworks |

**For research where training loop is frequently modified**: Direct visibility wins.

**Implementation**:
```python
# train.py (direct loop)
def train(config, ddp, rank, world_size, device):
    # Setup
    model, optimizers, data_loader = setup_training(...)

    # Training loop (all logic visible)
    for step in range(max_steps):
        # Update LR
        lrm = get_lr_multiplier(step)
        for opt in optimizers:
            for group in opt.param_groups:
                group['lr'] = group['initial_lr'] * lrm

        # Forward/backward
        for micro_step in range(grad_accum_steps):
            with autocast_ctx:
                output = model(x, y)
                loss = output.loss / grad_accum_steps
            loss.backward()
            x, y = next(data_loader)  # Prefetch

        # Optimizer step
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        for opt in optimizers:
            opt.step()
        model.zero_grad(set_to_none=True)

        # Logging, eval, checkpointing...
```

**Delete**: `src/trainer.py` (replaced by direct loop in train.py)

---

### 1.2 Architecture: Follow nanochat Strictly

**Decision**: Adopt ALL nanochat architecture features unconditionally (no config flags)

**Rationale**:
- These features are proven in modded-nanogpt SOTA speedruns
- Config flags add complexity without benefit
- We want clean, simple code
- Backward compatibility explicitly ignored

**Features adopted unconditionally**:

| Feature | nanochat | Old nano_gec | Impact |
|---------|----------|--------------|--------|
| **Positional encoding** | RoPE | Learned (wpe) | Better extrapolation |
| **Attention norm** | QK norm | None | Stability |
| **Weight tying** | Untied | Tied | More capacity |
| **MLP activation** | ReLU² | GELU | Faster training |
| **RMSNorm** | Functional (no γ) | Standard | Fewer params |
| **Linear bias** | No bias | Has bias | Fewer params |
| **Embedding dtype** | bfloat16 | float32 | Memory savings |
| **Norm position** | After embedding | Standard | From modded-nanogpt |
| **Initialization** | Zero-init outputs | GPT-2 style | Critical for Muon |

**No config files needed**: These are just the architecture now.

**Implementation**:
```python
# src/models/model_base.py
class BaseGPT(nn.Module):
    def __init__(self, config: ModelConfig):
        # NO wpe (learned positional embeddings)
        self.wte = nn.Embedding(vocab_size, n_embd)

        # Precompute RoPE embeddings
        self.rotary_seq_len = config.block_size * 10
        cos, sin = self._precompute_rotary_embeddings(...)
        self.register_buffer("cos", cos, persistent=False)
        self.register_buffer("sin", sin, persistent=False)

        # Transformer blocks
        self.blocks = nn.ModuleList([...])

        # Untied output head
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)
        # NO weight tying: wte.weight != lm_head.weight

        # Initialize
        self.apply(self._init_weights_nanochat)
        self._zero_init_outputs()  # Critical for Muon!

        # Cast embeddings to bfloat16
        self.wte.to(dtype=torch.bfloat16)

class BaseAttention(nn.Module):
    def forward(self, x):
        # Apply RoPE
        q, k = apply_rotary_emb(q, cos, sin), apply_rotary_emb(k, cos, sin)

        # QK norm (nanochat style - functional, no learnable params)
        q, k = norm(q), norm(k)

        # Attention
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return y

class DenseMLP(BaseMLP):
    def __init__(self, config: ModelConfig):
        # No bias!
        self.c_fc = nn.Linear(n_embd, 4 * n_embd, bias=False)
        self.c_proj = nn.Linear(4 * n_embd, n_embd, bias=False)

    def forward(self, x):
        x = self.c_fc(x)
        x = F.relu(x).square()  # ReLU²!
        x = self.c_proj(x)
        return x, {}

def norm(x):
    """Purely functional RMSNorm with no learnable params."""
    return F.rms_norm(x, (x.size(-1),))
```

---

### 1.3 GEC Integration: Use nanochat Components

**Decision**: Keep GEC routing logic in `src/models/gec/`, but use nanochat's components (no bias, ReLU²)

**Rationale**:
- GEC routing logic is nano_gec's unique contribution → preserve
- But GEC experts should use same components as dense model → nanochat style
- No need to extract to model_base (GEC-specific routing stays separate)

**Implementation**:
```python
# src/models/gec_shared/shared.py
class GECSharedMLP(BaseMLP):
    def __init__(self, config: ModelConfig):
        super().__init__(config)

        # Shared expert (nanochat style: no bias)
        self.shared_fc = nn.Linear(n_embd, shared_expert_dim, bias=False)
        self.shared_proj = nn.Linear(shared_expert_dim, n_embd, bias=False)

        # Routed experts (nanochat style: no bias)
        self.expert_fc = nn.Linear(n_embd, n_routed * expert_dim, bias=False)
        self.expert_proj = nn.Linear(n_routed * expert_dim, n_embd, bias=False)

        # Router (no bias)
        self.router = nn.Linear(n_embd, n_routed, bias=False)

    def forward(self, x):
        # Shared expert (ReLU² activation)
        shared = self.shared_fc(x)
        shared = F.relu(shared).square()  # nanochat activation!
        shared = self.shared_proj(shared)

        # GEC routing logic (unchanged - this is our contribution)
        router_logits = self.router(x)
        selected_indices, weights = self._select_topk_global(router_logits)

        # Expert computation (ReLU² activation)
        expert_out = self.expert_fc(selected_tokens)
        expert_out = F.relu(expert_out).square()  # nanochat activation!
        expert_out = self.expert_proj(expert_out)

        # Scatter and combine
        combined = scatter_add(expert_out, selected_indices, ...)
        output = shared + combined

        return output, metrics
```

**Changes needed**:
- Replace `nn.GELU()` → `F.relu(x).square()`
- Add `bias=False` to all Linear layers in GEC modules
- Keep all GEC routing logic unchanged

---

### 1.4 Data Loader: nanochat's Simple Streaming

**Decision**: Replace nano_gec's 285-line abstraction with nanochat's 50-line streaming approach

**Comparison**:

#### nano_gec's Current Approach (285 lines):
```python
# Complex abstraction with multiple backends
class DataBackend(ABC):
    @abstractmethod
    def get_batch(...): ...

class ShardedDataBackend(DataBackend):
    """Pre-tokenized .npy shards with mmap"""
    def get_batch(...):
        tokens = np.load(shard, mmap_mode='r')[pos:pos+n]
        return x, y

class LazyTokenizeBackend(DataBackend):
    """Tokenize on-the-fly with caching"""
    def get_batch(...):
        if cache_exists: load_cache()
        else: tokenize_and_cache()
        return x, y

class UnifiedDataLoader:
    """Facade using one backend"""
    def __init__(self, backend='sharded'|'lazy'):
        if backend == 'sharded':
            self.backend = ShardedDataBackend(...)
        elif backend == 'lazy':
            self.backend = LazyTokenizeBackend(...)
```

**Pros**: Flexible, can switch backends, fast with pre-tokenized data
**Cons**: 6x more code, abstraction overhead, overkill for pretraining

#### nanochat's Approach (50 lines):
```python
def tokenizing_distributed_data_loader(B, T, split):
    """
    Stream documents → tokenize on-the-fly → yield batches forever

    Simple architecture:
    - Infinite iterator over parquet files
    - Each rank reads different shards (start=rank, step=world_size)
    - Tokenize in batches
    - Maintain deque buffer of tokens
    - Pop from buffer when needed
    """
    token_buffer = deque()

    while True:  # Infinite
        # Stream documents
        for batch in parquets_iter_batched(split, start=rank, step=world_size):
            tokens = tokenizer.encode(batch, prepend=bos)
            for token_list in tokens:
                token_buffer.extend(token_list)

        # Yield batches from buffer
        while len(token_buffer) >= B*T+1:
            for i in range(B*T+1):
                scratch[i] = token_buffer.popleft()

            inputs = scratch[:-1].view(B, T).to("cuda")
            targets = scratch[1:].view(B, T).to("cuda")
            yield inputs, targets
```

**Pros**: 6x less code, proven at scale, memory efficient, simple
**Cons**: On-the-fly tokenization overhead (negligible with fast tokenizers)

**Why nanochat wins**:
1. **Proven at scale**: nanochat/modded-nanogpt use this exact approach
2. **Simplicity**: 50 vs 285 lines, easier to debug and modify
3. **Good enough**: Tokenization overhead is negligible with rustbpe
4. **Streaming**: Perfect for large pretraining datasets
5. **No abstraction needed**: We're doing pretraining, one data source, one format

**Implementation**:
```python
# src/data_loader.py (NEW, simplified to ~50 lines)

from collections import deque
import torch
from .utils.distributed import get_dist_info

def create_data_loader(
    data_path: str,
    batch_size: int,
    seq_len: int,
    tokenizer,
    split: str = "train",
):
    """nanochat-style streaming data loader."""
    ddp, rank, local_rank, world_size = get_dist_info()

    needed_tokens = batch_size * seq_len + 1
    bos_token = tokenizer.get_bos_token_id()
    token_buffer = deque()
    scratch = torch.empty(needed_tokens, dtype=torch.int64, pin_memory=True)

    # Infinite iterator
    def document_batches():
        while True:
            for batch in parquets_iter_batched(
                data_path, split=split,
                start=rank, step=world_size
            ):
                yield batch

    batches = document_batches()

    while True:
        # Fill buffer
        while len(token_buffer) < needed_tokens:
            doc_batch = next(batches)
            tokens = tokenizer.encode(doc_batch, prepend=bos_token)
            for token_list in tokens:
                token_buffer.extend(token_list)

        # Pop from buffer
        for i in range(needed_tokens):
            scratch[i] = token_buffer.popleft()

        # Create batch
        inputs = scratch[:-1].view(batch_size, seq_len).to("cuda", non_blocking=True)
        targets = scratch[1:].view(batch_size, seq_len).to("cuda", non_blocking=True)

        yield inputs, targets
```

**Delete**: Current 285-line `src/data_loader.py` with backend abstraction

---

### 1.5 Distributed Strategy: ZeRO-2 (No DDP)

**Decision**: Adopt nanochat's approach - no DDP wrapper, manual sync via optimizers

**nanochat's distributed strategy**:
- ✅ `dist.init_process_group()` (process group initialized)
- ❌ NO `DDP()` wrapper on model
- ✅ Model parameters: Fully replicated on all ranks
- ✅ Optimizer states: Sharded (ZeRO-2 style)
- ✅ Gradient sync: Manual `reduce_scatter` in optimizer
- ✅ Parameter sync: Manual `all_gather` in optimizer

**Why this works**:
1. **Model forward/backward**: Each rank has full model, computes gradients independently
2. **Gradient averaging**: `DistMuon`/`DistAdamW` do `reduce_scatter(AVG)` to average gradients
3. **Optimizer step**: Each rank updates its parameter shard (using sharded optimizer states)
4. **Parameter sync**: `all_gather` replicates updated parameters to all ranks

**vs Standard DDP**:
| Aspect | nanochat (ZeRO-2) | Standard DDP |
|--------|------------------|--------------|
| Model params | Replicated | Replicated |
| Optimizer states | **Sharded** | Replicated |
| Gradient sync | Manual (in optimizer) | Automatic (DDP hooks) |
| Parameter sync | Manual (in optimizer) | Automatic (via DDP) |
| Memory savings | Yes (optimizer states) | No |
| Complexity | Custom optimizers | DDP wrapper |

**Benefits**:
- ✅ Memory savings from sharded optimizer states
- ✅ More control over synchronization
- ✅ No DDP/compile interaction issues
- ✅ Proven at scale (nanochat multi-node training)

**Implementation**: Use `DistMuon` and `DistAdamW` (copied from nanochat)

---

## Part 2: File-by-File Implementation Plan

### Phase 1: Core Infrastructure (Optimizers + Distributed)

#### 2.1 Create `src/optimizers/` Module

**NEW file structure**:
```
src/optimizers/
├── __init__.py          # Exports
├── muon.py              # COPY from nanochat (Muon + DistMuon)
├── adamw_dist.py        # COPY from nanochat (DistAdamW)
└── factory.py           # NEW: Hybrid optimizer creation
```

**Files to copy directly** (no modifications):
- `nanochat/muon.py` → `src/optimizers/muon.py`
- `nanochat/adamw.py` → `src/optimizers/adamw_dist.py`

**NEW file** - `src/optimizers/factory.py`:
```python
"""
Optimizer factory for nanochat-style hybrid optimization.
Creates dual optimizers: Muon for matrices, AdamW for embeddings/lm_head.
"""

from typing import Tuple
import torch
import torch.nn as nn
from .muon import Muon, DistMuon
from .adamw_dist import DistAdamW

def create_hybrid_optimizer(
    model: nn.Module,
    unembedding_lr: float = 0.004,  # lm_head
    embedding_lr: float = 0.2,      # wte (50x higher!)
    matrix_lr: float = 0.02,        # transformer blocks (Muon)
    weight_decay: float = 0.0,
    model_dim: int = 768,
    use_dist: bool = False,
) -> Tuple[torch.optim.Optimizer, torch.optim.Optimizer]:
    """
    Create nanochat-style hybrid optimizer.

    Returns:
        (adamw_optimizer, muon_optimizer)
    """
    # Separate parameters by type
    matrix_params = []      # 2D params → Muon
    embedding_params = []   # wte → AdamW
    lm_head_params = []     # lm_head + other → AdamW

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue

        if 'wte' in name or 'token_embedding' in name:
            embedding_params.append(param)
        elif 'lm_head' in name:
            lm_head_params.append(param)
        elif param.ndim == 2:
            matrix_params.append(param)
        else:
            # 0D/1D params (layernorm, etc.) → AdamW
            lm_head_params.append(param)

    # μP-style LR scaling: lr ∝ 1/√d_model
    dmodel_lr_scale = (model_dim / 768) ** -0.5

    # AdamW groups
    adam_groups = [
        {'params': lm_head_params, 'lr': unembedding_lr * dmodel_lr_scale},
        {'params': embedding_params, 'lr': embedding_lr * dmodel_lr_scale},
    ]

    adamw_kwargs = dict(betas=(0.8, 0.95), eps=1e-10, weight_decay=weight_decay)

    # Create optimizers
    if use_dist:
        adamw_optimizer = DistAdamW(adam_groups, **adamw_kwargs)
        muon_optimizer = DistMuon(matrix_params, lr=matrix_lr, momentum=0.95)
    else:
        adamw_optimizer = torch.optim.AdamW(adam_groups, fused=True, **adamw_kwargs)
        muon_optimizer = Muon(matrix_params, lr=matrix_lr, momentum=0.95)

    # Mark initial LR for scheduling
    for opt in [adamw_optimizer, muon_optimizer]:
        for group in opt.param_groups:
            group['initial_lr'] = group['lr']

    return adamw_optimizer, muon_optimizer
```

**DELETE**: `src/optimizer.py` (replaced by optimizers/ module)

---

#### 2.2 Create `src/utils/distributed.py`

**Purpose**: Centralize distributed utilities from nanochat

```python
"""
Distributed training utilities adapted from nanochat.
Handles multi-GPU coordination without DDP wrapper.
"""

import os
import torch
import torch.distributed as dist

def is_ddp() -> bool:
    """Check if running in distributed mode."""
    return int(os.environ.get('RANK', -1)) != -1

def get_dist_info() -> tuple[bool, int, int, int]:
    """
    Get distributed training info.

    Returns:
        (is_distributed, rank, local_rank, world_size)
    """
    if is_ddp():
        assert all(var in os.environ for var in ['RANK', 'LOCAL_RANK', 'WORLD_SIZE'])
        return (
            True,
            int(os.environ['RANK']),
            int(os.environ['LOCAL_RANK']),
            int(os.environ['WORLD_SIZE'])
        )
    else:
        return False, 0, 0, 1

def print0(s="", **kwargs):
    """Print only on rank 0."""
    if int(os.environ.get('RANK', 0)) == 0:
        print(s, **kwargs)

def compute_init(seed: int = 42):
    """
    Initialize compute environment (CUDA, distributed, precision).

    Returns:
        (is_distributed, rank, local_rank, world_size, device)
    """
    assert torch.cuda.is_available(), "CUDA required"

    # Reproducibility
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)

    # Precision: TF32 for matmuls
    torch.set_float32_matmul_precision("high")

    # Distributed setup
    ddp, rank, local_rank, world_size = get_dist_info()

    if ddp:
        device = torch.device("cuda", local_rank)
        torch.cuda.set_device(device)
        dist.init_process_group(backend="nccl", device_id=device)
        dist.barrier()
        print0(f"Initialized distributed: {world_size} GPUs")
    else:
        device = torch.device("cuda")
        print0("Single GPU training")

    return ddp, rank, local_rank, world_size, device

def compute_cleanup():
    """Cleanup distributed process group."""
    if is_ddp():
        dist.destroy_process_group()
```

---

### Phase 2: Model Architecture Updates

#### 2.3 Refactor `src/models/model_base.py`

**Major changes**:
1. Remove learned positional embeddings (`wpe`)
2. Add RoPE embeddings
3. Add QK norm to attention
4. Untie embeddings (no weight tying)
5. Use ReLU² activation
6. Functional RMSNorm (no learnable γ)
7. No bias in linear layers
8. nanochat initialization (zero-init outputs)
9. Cast embeddings to bfloat16

**Updated ModelConfig**:
```python
@dataclass
class ModelConfig:
    # Core parameters (unchanged)
    vocab_size: int = 50304
    block_size: int = 1024
    n_layer: int = 12
    n_head: int = 12
    n_embd: int = 768

    # MoE parameters (unchanged)
    model_type: str = "dense"  # dense, gec, gec_shared, ec
    granularity: int = 2
    expansion: int = 4
    router_activation: str = "sigmoid"
    normalization_mode: str = "fanout"

    # nanochat features (NO CONFIG FLAGS - these are just the architecture)
    # All features unconditionally adopted from nanochat
```

**Helper functions**:
```python
def norm(x):
    """Purely functional RMSNorm with no learnable params (nanochat style)."""
    return F.rms_norm(x, (x.size(-1),))

def apply_rotary_emb(x, cos, sin):
    """Apply rotary embeddings (from nanochat)."""
    assert x.ndim == 4  # multihead attention
    d = x.shape[3] // 2
    x1, x2 = x[..., :d], x[..., d:]
    y1 = x1 * cos + x2 * sin
    y2 = x1 * (-sin) + x2 * cos
    return torch.cat([y1, y2], 3)
```

**Updated BaseAttention**:
```python
class BaseAttention(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        assert config.n_embd % config.n_head == 0

        # No bias!
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd, bias=False)
        self.c_proj = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.n_head = config.n_head
        self.n_embd = config.n_embd

        # Causal mask
        self.register_buffer(
            "mask",
            torch.tril(torch.ones(config.block_size, config.block_size))
        )

    def forward(self, x: torch.Tensor, cos_sin) -> torch.Tensor:
        B, T, C = x.size()

        # QKV projection
        qkv = self.c_attn(x)
        q, k, v = qkv.split(self.n_embd, dim=2)

        # Reshape for multi-head
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)

        # Apply RoPE (nanochat style)
        cos, sin = cos_sin
        q = apply_rotary_emb(q, cos, sin)
        k = apply_rotary_emb(k, cos, sin)

        # QK norm (nanochat style - functional)
        q = norm(q)
        k = norm(k)

        # Attention
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)

        # Reshape back
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        y = self.c_proj(y)
        return y
```

**Updated DenseMLP**:
```python
class DenseMLP(BaseMLP):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        # No bias!
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd, bias=False)
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd, bias=False)

    def forward(self, x: torch.Tensor):
        h = self.c_fc(x)
        h = F.relu(h).square()  # ReLU² (nanochat style)
        h = self.c_proj(h)
        return h, {}
```

**Updated BaseGPT**:
```python
class BaseGPT(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Token embedding only (NO wpe!)
        self.wte = nn.Embedding(config.vocab_size, config.n_embd)

        # Precompute RoPE embeddings
        self.rotary_seq_len = config.block_size * 10
        head_dim = config.n_embd // config.n_head
        cos, sin = self._precompute_rotary_embeddings(self.rotary_seq_len, head_dim)
        self.register_buffer("cos", cos, persistent=False)
        self.register_buffer("sin", sin, persistent=False)

        # Transformer blocks
        mlp_class = self._get_mlp_class()
        self.blocks = nn.ModuleList([
            TransformerBlock(config, mlp_class, layer_idx=i)
            for i in range(config.n_layer)
        ])

        # Output
        self.ln_f = nn.LayerNorm(config.n_embd)  # Uses functional norm internally
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)

        # NO weight tying (nanochat: untied embeddings)
        # self.wte.weight = self.lm_head.weight  ← DELETE THIS

        # Initialize (nanochat style)
        self.apply(self._init_weights_nanochat)
        self._zero_init_outputs()  # Critical for Muon!

        # Cast embeddings to bfloat16
        self.wte.to(dtype=torch.bfloat16)

    def _init_weights_nanochat(self, module):
        """nanochat-style initialization."""
        if isinstance(module, nn.Linear):
            # Custom fan-in with aspect ratio
            fan_out = module.weight.size(0)
            fan_in = module.weight.size(1)
            std = 1.0 / math.sqrt(fan_in) * min(1.0, math.sqrt(fan_out / fan_in))
            torch.nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=1.0)

    def _zero_init_outputs(self):
        """Zero-init all output projections (critical for Muon!)."""
        torch.nn.init.zeros_(self.lm_head.weight)
        for block in self.blocks:
            if hasattr(block.mlp, 'c_proj'):
                torch.nn.init.zeros_(block.mlp.c_proj.weight)
            torch.nn.init.zeros_(block.attn.c_proj.weight)

    def _precompute_rotary_embeddings(self, seq_len, head_dim, base=10000, device=None):
        """Precompute RoPE embeddings (from nanochat)."""
        if device is None:
            device = self.wte.weight.device

        channel_range = torch.arange(0, head_dim, 2, dtype=torch.float32, device=device)
        inv_freq = 1.0 / (base ** (channel_range / head_dim))
        t = torch.arange(seq_len, dtype=torch.float32, device=device)
        freqs = torch.outer(t, inv_freq)
        cos, sin = freqs.cos(), freqs.sin()

        # Keep in bfloat16
        cos, sin = cos.bfloat16(), sin.bfloat16()
        # Add batch and head dims
        cos = cos[None, :, None, :]
        sin = sin[None, :, None, :]

        return cos, sin

    def forward(self, input_ids, labels=None):
        device = input_ids.device
        B, T = input_ids.size()

        # Token embeddings only (no positional)
        x = self.wte(input_ids)
        x = norm(x)  # Norm after embedding (nanochat)

        # Get RoPE for current sequence
        cos_sin = self.cos[:, :T], self.sin[:, :T]

        # Forward through blocks
        all_metrics = {}
        layer_data = {} if not self.training else None

        for i, block in enumerate(self.blocks):
            x, block_metrics = block(x, cos_sin)  # Pass RoPE

            # Aggregate metrics
            for k, v in block_metrics.items():
                if k not in all_metrics:
                    all_metrics[k] = []
                all_metrics[k].append(v)

        # Final norm and output
        x = norm(x)  # Functional norm
        logits = self.lm_head(x)

        # Compute loss if labels provided
        loss = None
        if labels is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), labels.view(-1))

        # Aggregate metrics
        aggregated_metrics = {}
        for k, v_list in all_metrics.items():
            if v_list:
                aggregated_metrics[k] = torch.stack(v_list).mean()

        return ModelOutput(logits=logits, loss=loss, metrics=aggregated_metrics)
```

**Updated TransformerBlock**:
```python
class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig, mlp_class: type, layer_idx: int = 0):
        super().__init__()
        self.layer_idx = layer_idx
        self.attn = BaseAttention(config)
        self.mlp = mlp_class(config)

    def forward(self, x: torch.Tensor, cos_sin) -> Tuple[torch.Tensor, Dict]:
        # Attention (pass RoPE)
        x = x + self.attn(norm(x), cos_sin)

        # MLP
        mlp_out, metrics = self.mlp(norm(x))
        x = x + mlp_out

        return x, metrics
```

---

#### 2.4 Update GEC Modules

**Apply nanochat components to all GEC variants**:

```python
# src/models/gec_shared/shared.py

class GECSharedMLP(BaseMLP):
    def __init__(self, config: ModelConfig):
        super().__init__(config)

        # Shared expert (no bias!)
        self.shared_fc = nn.Linear(config.n_embd, config.shared_expert_dim, bias=False)
        self.shared_proj = nn.Linear(config.shared_expert_dim, config.n_embd, bias=False)

        # Routed experts (no bias!)
        n_routed = config.n_experts - 1
        self.expert_fc = nn.Linear(config.n_embd, n_routed * config.expert_dim, bias=False)
        self.expert_proj = nn.Linear(n_routed * config.expert_dim, config.n_embd, bias=False)

        # Router (no bias!)
        self.router = nn.Linear(config.n_embd, n_routed, bias=False)

    def forward(self, x):
        B, T, C = x.shape

        # Shared expert (ReLU²!)
        shared = self.shared_fc(x)
        shared = F.relu(shared).square()  # nanochat activation
        shared = self.shared_proj(shared)

        # GEC routing logic (unchanged - our contribution)
        router_logits = self.router(x)

        # Global top-k selection
        router_logits_flat = router_logits.view(-1, n_routed)
        selected_indices, weights = self._select_topk_global(router_logits_flat)

        # Expert computation (ReLU²!)
        selected_tokens = x.view(-1, C)[selected_indices // n_routed]
        expert_out = self.expert_fc(selected_tokens)
        expert_out = F.relu(expert_out).square()  # nanochat activation
        expert_out = self.expert_proj(expert_out)

        # Scatter and normalize
        combined = self._scatter_and_normalize(
            expert_out, selected_indices, weights, B * T
        )

        # Add shared and routed
        output = shared + combined

        return output, metrics
```

**Same changes for**:
- `src/models/gec/gec.py`
- `src/models/ec.py`

**Pattern**:
1. Replace all `nn.Linear(..., bias=True)` → `bias=False`
2. Replace all `nn.GELU()` → `F.relu(x).square()`
3. Keep all GEC routing logic unchanged

---

### Phase 3: Training Loop

#### 2.5 Create NEW `train.py` (Direct Loop)

**Structure**:
```python
#!/usr/bin/env python3
"""Main training script - nanochat style direct loop with Hydra config."""

import hydra
from omegaconf import DictConfig, OmegaConf
import torch
import time
from pathlib import Path

from src.config import Config
from src.models import BaseGPT, ModelConfig
from src.data_loader import create_data_loader
from src.optimizers import create_hybrid_optimizer
from src.utils.distributed import compute_init, compute_cleanup, print0
from src.utils.logger import Logger
from src.utils.metrics import MetricsTracker


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    """Entry point with Hydra."""
    config = Config.from_dict(OmegaConf.to_container(cfg, resolve=True))
    config.validate()

    # Initialize compute
    ddp, rank, local_rank, world_size, device = compute_init(seed=42)

    try:
        train(config, ddp, rank, local_rank, world_size, device)
    finally:
        compute_cleanup()


def train(config, ddp, rank, local_rank, world_size, device):
    """Direct training loop (nanochat style)."""

    master_process = rank == 0

    # =========================================================================
    # SETUP
    # =========================================================================

    # Model
    model_config = ModelConfig(**config.model)
    with torch.device("meta"):
        model = BaseGPT(model_config)
    model.to_empty(device=device)

    orig_model = model  # For checkpointing

    # Compile (NO DDP wrapper!)
    if config.training.compile_model:
        model = torch.compile(model, dynamic=False)
        print0("Model compiled")

    num_params = sum(p.numel() for p in orig_model.parameters())
    print0(f"Parameters: {num_params:,}")

    # Data
    grad_accum_steps = config.training.validate_batch_settings(world_size)
    print0(f"Gradient accumulation: {grad_accum_steps}")

    data_loader = create_data_loader(
        data_path=config.data.data_path,
        batch_size=config.training.per_device_batch_size,
        seq_len=config.training.sequence_length,
        tokenizer=get_tokenizer(),
        split="train",
    )

    # Optimizers (Hybrid: AdamW + Muon)
    adamw_optimizer, muon_optimizer = create_hybrid_optimizer(
        model=orig_model,
        unembedding_lr=config.optimizer.unembedding_lr,
        embedding_lr=config.optimizer.embedding_lr,
        matrix_lr=config.optimizer.matrix_lr,
        weight_decay=config.training.weight_decay,
        model_dim=model_config.n_embd,
        use_dist=ddp,
    )
    optimizers = [adamw_optimizer, muon_optimizer]

    # LR schedule (nanochat style: constant + warmdown)
    max_steps = config.training.calculate_max_steps()
    warmup_ratio = config.optimizer.warmup_ratio
    warmdown_ratio = config.optimizer.warmdown_ratio
    final_lr_frac = config.optimizer.final_lr_frac

    def get_lr_multiplier(it):
        warmup_iters = round(warmup_ratio * max_steps)
        warmdown_iters = round(warmdown_ratio * max_steps)
        if it < warmup_iters:
            return (it + 1) / warmup_iters
        elif it <= max_steps - warmdown_iters:
            return 1.0  # Constant!
        else:
            progress = (max_steps - it) / warmdown_iters
            return progress * 1.0 + (1 - progress) * final_lr_frac

    # Muon momentum schedule
    def get_muon_momentum(it):
        frac = min(it / 300, 1)
        return (1 - frac) * 0.85 + frac * 0.95

    # Logging
    output_dir = Path(config.output_dir) / config.experiment_name
    if master_process:
        output_dir.mkdir(parents=True, exist_ok=True)

    logger = Logger(config=config.logging, output_dir=output_dir, rank=rank)
    metrics = MetricsTracker()

    # Mixed precision
    autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)

    # =========================================================================
    # TRAINING LOOP (nanochat direct style)
    # =========================================================================

    # Prefetch first batch
    x, y = next(data_loader)

    for step in range(max_steps):
        t0 = time.time()

        # Update learning rates
        lrm = get_lr_multiplier(step)
        for opt in optimizers:
            for group in opt.param_groups:
                group['lr'] = group['initial_lr'] * lrm

        # Update Muon momentum
        muon_momentum = get_muon_momentum(step)
        for group in muon_optimizer.param_groups:
            group['momentum'] = muon_momentum

        # Forward/backward with gradient accumulation
        model.train()
        total_loss = 0.0

        for micro_step in range(grad_accum_steps):
            with autocast_ctx:
                output = model(x, y)
                loss = output.loss / grad_accum_steps

            total_loss += loss.item()
            loss.backward()

            # Prefetch next batch while GPU busy
            x, y = next(data_loader)

        # Gradient clipping
        if config.training.grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(
                orig_model.parameters(),
                config.training.grad_clip
            )

        # Optimizer step (both optimizers)
        for opt in optimizers:
            opt.step()

        model.zero_grad(set_to_none=True)

        torch.cuda.synchronize()
        t1 = time.time()

        # Logging
        step_time = t1 - t0
        tokens_per_step = config.training.total_batch_size

        step_metrics = {
            'loss': total_loss,
            'learning_rate': lrm * config.optimizer.matrix_lr,
            'throughput': tokens_per_step / step_time,
            'step_time': step_time,
        }

        if step % config.logging.log_interval == 0:
            logger.log_metrics(step, step_metrics)

        # Evaluation
        if step % config.training.eval_interval == 0 and step > 0:
            evaluate(model, data_loader, config, logger, step)

        # Checkpointing
        if master_process and step % config.training.save_interval == 0 and step > 0:
            save_checkpoint(output_dir, step, orig_model, optimizers, config)

    # Final checkpoint
    if master_process:
        save_checkpoint(output_dir, max_steps, orig_model, optimizers, config)

    print0("Training complete!")


def evaluate(model, data_loader, config, logger, step):
    """Evaluation (simplified)."""
    model.eval()
    total_loss = 0.0
    num_batches = 10

    with torch.no_grad():
        for _ in range(num_batches):
            x, y = next(data_loader)
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                output = model(x, y)
            total_loss += output.loss.item()

    eval_loss = total_loss / num_batches
    logger.log_metrics(step, {'eval_loss': eval_loss}, prefix="eval/")
    model.train()


def save_checkpoint(output_dir, step, model, optimizers, config):
    """Save checkpoint."""
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)

    checkpoint = {
        'step': step,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dicts': [opt.state_dict() for opt in optimizers],
        'config': config.to_dict(),
    }

    checkpoint_path = checkpoint_dir / f"checkpoint_step_{step}.pt"
    torch.save(checkpoint, checkpoint_path)
    print0(f"Saved: {checkpoint_path}")


if __name__ == "__main__":
    main()
```

**DELETE**: `src/trainer.py` (replaced by direct loop)

---

### Phase 4: Configuration

#### 2.6 Update Config Files

**NEW config group** - `configs/optimizer/nanochat.yaml`:
```yaml
# nanochat-style hybrid optimizer configuration

# Per-parameter learning rates (these are the key!)
unembedding_lr: 0.004  # lm_head (baseline)
embedding_lr: 0.2      # wte (50x higher!)
matrix_lr: 0.02        # Muon for transformer blocks (5x higher)

# AdamW hyperparameters (for embeddings/lm_head)
adamw_betas: [0.8, 0.95]
adamw_eps: 1.0e-10

# Muon hyperparameters
muon_momentum: 0.95
muon_nesterov: true
muon_ns_steps: 5

# LR schedule (nanochat style)
warmup_ratio: 0.0      # No warmup!
warmdown_ratio: 0.2    # Linear decay last 20%
final_lr_frac: 0.0     # Decay to 0

# Muon momentum warmup
muon_momentum_warmup_steps: 300
muon_momentum_start: 0.85
muon_momentum_end: 0.95
```

**Update `configs/config.yaml`**:
```yaml
defaults:
  - model_size: tiny
  - mlp: gec_shared
  - optimizer: nanochat       # NEW default
  - experiment: debug
  - _self_

# ... rest unchanged ...
```

**No `configs/model_arch/` needed** - nanochat features are unconditional!

---

## Part 3: Summary of Changes

### Files to COPY (no modification):
- ✅ `nanochat/muon.py` → `src/optimizers/muon.py`
- ✅ `nanochat/adamw.py` → `src/optimizers/adamw_dist.py`

### Files to CREATE:
- ✅ `src/optimizers/__init__.py`
- ✅ `src/optimizers/factory.py`
- ✅ `src/utils/distributed.py`
- ✅ `train.py` (NEW, direct loop)
- ✅ `configs/optimizer/nanochat.yaml`

### Files to REFACTOR:
- ✅ `src/models/model_base.py` (RoPE, QK norm, ReLU², no bias, nanochat init)
- ✅ `src/models/gec_shared/shared.py` (ReLU², no bias)
- ✅ `src/models/gec/gec.py` (ReLU², no bias)
- ✅ `src/models/ec.py` (ReLU², no bias)
- ✅ `src/data_loader.py` (simplify to streaming, 50 lines)
- ✅ `configs/config.yaml` (add optimizer default)

### Files to DELETE:
- ❌ `src/trainer.py` (replaced by direct loop in train.py)
- ❌ `src/optimizer.py` (replaced by optimizers/ module)
- ❌ Old 285-line data_loader.py abstraction

### Files UNCHANGED:
- ✅ `src/models/gec/` routing logic (our contribution)
- ✅ `src/kernels/` (Triton kernels)
- ✅ `src/utils/metrics.py`
- ✅ `src/utils/visualizer.py`
- ✅ `benchmark/` (should work with import fixes only)
- ✅ All Hydra configs except optimizer/

---

## Part 4: Key Architectural Changes Summary

### What Changes Unconditionally:

| Component | Old (nano_gec) | New (nanochat) |
|-----------|---------------|----------------|
| **Positional encoding** | Learned (wpe) | RoPE |
| **Attention norm** | None | QK norm |
| **Weight tying** | Tied | Untied |
| **MLP activation** | GELU | ReLU² |
| **RMSNorm** | Learnable γ | Functional (no params) |
| **Linear bias** | bias=True | bias=False |
| **Embedding dtype** | float32 | bfloat16 |
| **Init** | GPT-2 + depth scaling | nanochat (zero outputs) |
| **Optimizer** | Single AdamW | Dual (AdamW + Muon) |
| **LR schedule** | Cosine | Constant + warmdown |
| **Distributed** | DDP wrapper | No DDP (manual sync) |
| **Data loader** | 285 lines, abstracted | 50 lines, streaming |

### What Stays the Same:

| Component | Status |
|-----------|--------|
| **GEC routing logic** | Unchanged (our contribution) |
| **Triton kernels** | Unchanged |
| **Hydra config system** | Unchanged (superior) |
| **Metrics tracking** | Unchanged |
| **Visualizations** | Unchanged |
| **Benchmarks** | Unchanged (import fixes only) |

---

## Part 5: Expected Performance Gains

Based on nanochat/modded-nanogpt results:

1. **35% speedup** from Muon optimizer
2. **Faster convergence** from constant LR + warmdown
3. **Better stability** from zero-init + QK norm
4. **Memory savings** from ZeRO-2 optimizer sharding

**Total expected**: ~40-50% faster to same validation loss.

---

## Part 6: Implementation Checklist

### Phase 1: Foundation (Week 1)
- [ ] Copy `muon.py`, `adamw_dist.py`
- [ ] Create `optimizers/factory.py`
- [ ] Create `utils/distributed.py`
- [ ] Test optimizers in isolation

### Phase 2: Model (Week 1-2)
- [ ] Update `ModelConfig` (remove arch flags)
- [ ] Add RoPE to `BaseAttention`
- [ ] Add QK norm to `BaseAttention`
- [ ] Update `DenseMLP` (ReLU², no bias)
- [ ] Update `BaseGPT` (untied, init, bfloat16)
- [ ] Update GEC modules (ReLU², no bias)
- [ ] Test model creation + forward pass

### Phase 3: Training (Week 2)
- [ ] Create new `train.py` with direct loop
- [ ] Add LR schedule functions
- [ ] Add data prefetching
- [ ] Test single-GPU training

### Phase 4: Data (Week 2)
- [ ] Simplify `data_loader.py` to streaming
- [ ] Test data loading

### Phase 5: Integration (Week 2-3)
- [ ] Create optimizer configs
- [ ] Update default config
- [ ] Test multi-GPU training
- [ ] Verify benchmarks still work

### Phase 6: Cleanup (Week 3)
- [ ] Delete `trainer.py`
- [ ] Delete old `optimizer.py`
- [ ] Delete old data loader
- [ ] Update documentation

---

## Part 7: Risks and Mitigations

### Risk 1: Muon + MoE Incompatibility
**Risk**: Muon has never been tested with MoE architectures
**Mitigation**:
- Muon only affects matrix params, GEC routing is separate
- Start with dense model, then test GEC
- If issues, can fall back to AdamW for all params

### Risk 2: Zero-init + MoE Instability
**Risk**: Zero-init might cause instability with sparse routing
**Mitigation**:
- Monitor gradient norms carefully
- May need to adjust init scale for router
- Can start with small learning rates

### Risk 3: Compilation Issues
**Risk**: torch.compile + no DDP might have edge cases
**Mitigation**:
- Test thoroughly on single GPU first
- nanochat/modded-nanogpt use this exact setup
- Can disable compile for debugging

### Risk 4: Data Loading Performance
**Risk**: On-the-fly tokenization might be slow
**Mitigation**:
- nanochat uses fast rustbpe tokenizer
- Overhead is negligible in practice
- Can profile if needed

---

## Conclusion

This plan provides a complete roadmap for integrating nanochat's techniques into nano_gec:

**What we gain**:
- ✅ 35%+ speedup from Muon
- ✅ Faster convergence from constant LR
- ✅ Better stability from modern arch
- ✅ Simpler codebase (fewer lines)
- ✅ Proven techniques from SOTA

**What we preserve**:
- ✅ GEC routing (our contribution)
- ✅ Triton kernels
- ✅ Hydra config system
- ✅ Metrics and visualization

**Philosophy**:
- 🔥 Strict adherence to nanochat architecture (no config flags)
- 🔥 Ignore backward compatibility
- 🔥 Simplify ruthlessly (50-line data loader, direct training loop)
- 🔥 Keep what's unique (GEC, Hydra, metrics)

Ready for implementation!
