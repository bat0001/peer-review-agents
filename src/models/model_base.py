"""Base model architecture for GPT2 variants with clean plugin system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, Union
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


# Helper functions for nanochat-style architecture

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
    out = torch.cat([y1, y2], 3)
    out = out.to(x.dtype)  # Ensure input/output dtypes match (nanochat)
    return out


@dataclass
class ModelConfig:
    """Unified model configuration.

    Following "Scaling Laws for Fine-Grained Mixture of Experts" notation:
    - G (granularity) = dff / dexpert, where dff = 4 × n_embd
    - E (expansion) = total MoE params / dense FFN params
    - n_experts = G × E
    - expert_dim = dff / G = (4 × n_embd) / G
    - For compute-matching with dense: E × selection_rate ≈ 1
    """
    # Core model parameters
    vocab_size: int = 50304
    block_size: int = 1024
    n_layer: int = 12
    n_head: int = 12
    n_embd: int = 768

    # Model variant
    model_type: str = "dense"  # dense, gec, gec_shared, ec, scattermoe_tc, tc_shared
    first_layer_dense: bool = False  # Use dense MLP for layer 0 (no routing)

    # MoE/GEC parameters (new paper notation)
    granularity: int = 2       # G: ratio of FFN dim to expert dim (dff / dexpert), must be power of 2
    expansion: int = 4         # E: expansion rate (total params / dense params)

    # Routing configuration
    routing_chunk_seqs: Optional[int] = None  # Number of sequences per routing chunk (None=global)
    router_activation: str = "sigmoid"  # Router activation: sigmoid, relu, softmax_k, softmax_e, softmax_e_shared_out
    normalization_mode: str = "fanout"  # fanout (divide by fanout+1), none (use weights as-is, for softmax_e)
    routing_mode: str = "topk"  # Routing mode (training only): 'topk' or 'threshold'
    threshold_warmup_steps: int = -1  # Passed from training config; -1 = disabled, >=0 = switch at step N
    expert_capacity_factor: float = -1.0  # Capacity bounds: [k×(1-cap), k×(1+cap)] for threshold routing (-1=disabled)
    cutoff_ema_alpha: float = 0.99  # EMA decay for cutoff tracking (higher = slower adaptation)

    # Token-choice load balancing (scattermoe_tc, tc_shared)
    load_balance_method: str = "none"  # "none" | "aux" | "aux_error" | "deepseek"
    aux_loss_coef: float = 0.0
    deepseek_bias_lr: float = 0.0
    z_loss_coef: float = 0.0

    # Scatter backend configuration
    scatter_backend: str = "index_add"  # 'index_add', 'index_add_fp32', 'csr', or 'csr_optimized'

    # Expert parallelism (EP): shard experts across GPUs instead of replicating
    expert_parallel: bool = False

    # Derived parameters (computed in __post_init__)
    n_experts: Optional[int] = None       # Computed as G × E
    expert_dim: Optional[int] = None      # Computed as (4 × n_embd) / G
    shared_expert_dim: Optional[int] = None  # For GEC shared expert, default to expert_dim
    selection_rate: Optional[float] = None  # Computed for compute-matching (or can override)

    # Legacy parameters (for backward compatibility)
    density: Optional[float] = None  # Deprecated: legacy parameter

    # Regularization
    weight_decay: float = 0.1

    def __post_init__(self):
        # Normalize model type aliases
        if self.model_type == "tc":
            self.model_type = "scattermoe_tc"

        # Validate model type
        assert self.model_type in ["dense", "gec", "gec_shared", "gec_shared_capacity", "ec", "ec_shared", "scattermoe_tc", "tc_shared"]

        # Validate router activation
        if self.model_type in ["gec", "gec_shared", "gec_shared_capacity", "ec", "ec_shared", "scattermoe_tc", "tc_shared"]:
            assert self.router_activation in ["sigmoid", "relu", "softmax_k", "softmax_e", "softmax_e_shared_out"], \
                f"router_activation must be one of [sigmoid, relu, softmax_k, softmax_e, softmax_e_shared_out], got {self.router_activation}"
            if self.model_type in ["scattermoe_tc", "tc_shared"]:
                assert self.router_activation != "softmax_k", \
                    "router_activation='softmax_k' is not supported for token-choice routing"
            if self.model_type == "tc_shared":
                assert self.router_activation != "softmax_e_shared_out", \
                    "router_activation='softmax_e_shared_out' is not supported for tc_shared"

        # Validate routing mode (training only; eval always uses threshold)
        if self.routing_mode not in ["topk", "threshold"]:
            raise ValueError(
                f"routing_mode must be 'topk' or 'threshold', got {self.routing_mode}"
            )

        if self.load_balance_method not in ["none", "aux", "aux_error", "deepseek"]:
            raise ValueError(
                "load_balance_method must be one of ['none', 'aux', 'aux_error', 'deepseek'], "
                f"got {self.load_balance_method}"
            )

        # Validate granularity is a power of 2 (for integer expert_dim)
        if self.model_type in ["gec", "gec_shared", "gec_shared_capacity", "ec", "ec_shared", "scattermoe_tc", "tc_shared"]:
            G = self.granularity
            assert G > 0 and (G & (G - 1)) == 0, \
                f"granularity must be a power of 2, got {G}"
            if self.model_type in ["gec_shared", "gec_shared_capacity", "gec_shared_csr", "ec_shared", "tc_shared"]:
                assert G >= 2, \
                    f"{self.model_type} requires granularity >= 2 (need routed experts), got {G}"

        # Backward compatibility: handle legacy density/selection_rate
        if self.density is not None:
            import warnings
            warnings.warn(
                "Parameter 'density' is deprecated and will be ignored. "
                "Selection rate is now automatically computed for compute-matching.",
                DeprecationWarning
            )

        # Compute derived parameters
        dff = 4 * self.n_embd  # Standard FFN intermediate dimension

        # If n_experts and expert_dim are explicitly provided (legacy mode),
        # derive G and E from them
        if self.n_experts is not None and self.expert_dim is not None:
            # Backward compatibility path
            pass  # Keep the provided values
        else:
            # New notation: derive from G and E
            # GEC/EC: n_experts = G × E
            # GEC_shared/EC_shared: n_experts = (G × E) + 1 (routed + 1 shared)
            if self.model_type in ["gec_shared", "gec_shared_capacity", "gec_shared_csr", "ec_shared", "tc_shared"]:
                self.n_experts = int(self.granularity * self.expansion) + 1
            else:
                self.n_experts = int(self.granularity * self.expansion)
            self.expert_dim = dff // self.granularity

        # Set shared expert dim if not specified
        if self.shared_expert_dim is None:
            self.shared_expert_dim = self.expert_dim


@dataclass
class ModelOutput:
    """Unified output format for all model variants."""
    logits: torch.Tensor
    loss: Optional[torch.Tensor] = None
    metrics: Dict[str, torch.Tensor] = field(default_factory=dict)
    layer_data: Optional[Dict[int, Dict[str, torch.Tensor]]] = None  # Per-layer data for visualization


@dataclass
class EvalBatchForwardResult:
    """Eval-prefill output format for batched scoring paths."""
    losses: torch.Tensor
    predictions: torch.Tensor
    valid_rows: torch.Tensor


class BaseAttention(nn.Module):
    """Causal self-attention module with RoPE and QK norm (nanochat style)."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        assert config.n_embd % config.n_head == 0

        # No bias! (nanochat style)
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd, bias=False)
        self.c_proj = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.n_head = config.n_head
        self.n_embd = config.n_embd

        # Causal mask (kept for reference, but scaled_dot_product_attention handles it)
        self.register_buffer(
            "mask",
            torch.tril(torch.ones(config.block_size, config.block_size))
            .view(1, 1, config.block_size, config.block_size)
        )

    def forward(self, x: torch.Tensor, cos_sin: Tuple[torch.Tensor, torch.Tensor]) -> torch.Tensor:
        B, T, C = x.size()

        # QKV projection
        qkv = self.c_attn(x)
        q, k, v = qkv.split(self.n_embd, dim=2)

        # Reshape for multi-head attention (but don't transpose yet)
        k = k.view(B, T, self.n_head, C // self.n_head)
        q = q.view(B, T, self.n_head, C // self.n_head)
        v = v.view(B, T, self.n_head, C // self.n_head)

        # Apply RoPE before transpose (nanochat style)
        cos, sin = cos_sin
        q = apply_rotary_emb(q, cos, sin)
        k = apply_rotary_emb(k, cos, sin)

        # QK norm (nanochat style - functional)
        q = norm(q)
        k = norm(k)

        # Now transpose for attention computation
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)

        # Attention
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)

        # Reshape back
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        y = self.c_proj(y)
        return y


class BaseMLP(nn.Module, ABC):
    """Abstract base class for MLP variants."""
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
    
    @abstractmethod
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """
        Forward pass returning output and metrics.
        
        Args:
            x: Input tensor of shape (B, T, C)
            
        Returns:
            output: Output tensor of shape (B, T, C)
            metrics: Dictionary of metrics (e.g., expert usage)
        """
        pass


class DenseMLP(BaseMLP):
    """Standard dense MLP with ReLU² activation (nanochat style)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        # No bias! (nanochat style)
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd, bias=False)
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd, bias=False)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        h = self.c_fc(x)
        h = F.relu(h).square()  # ReLU² (nanochat style)
        h = self.c_proj(h)
        return h, {}


class TransformerBlock(nn.Module):
    """Transformer block with configurable MLP and functional norm (nanochat style)."""

    def __init__(self, config: ModelConfig, mlp_class: type, layer_idx: int = 0):
        super().__init__()
        self.layer_idx = layer_idx
        self.attn = BaseAttention(config)
        self.mlp = mlp_class(config)

        import inspect
        self.mlp_needs_layer_idx = 'layer_idx' in inspect.signature(self.mlp.forward).parameters

    def forward(self, x: torch.Tensor, cos_sin: Tuple[torch.Tensor, torch.Tensor]) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        # Attention with pre-norm (functional norm, nanochat style)
        x = x + self.attn(norm(x), cos_sin)

        # MLP with pre-norm (functional norm, nanochat style)
        mlp_out, metrics = (self.mlp(norm(x), layer_idx=self.layer_idx) if self.mlp_needs_layer_idx
                            else self.mlp(norm(x)))
        x = x + mlp_out

        return x, metrics


class BaseGPT(nn.Module):
    """Base GPT model with nanochat architecture: RoPE, no bias, untied embeddings."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Token embedding only (NO wpe! - nanochat style)
        self.wte = nn.Embedding(config.vocab_size, config.n_embd)

        # Precompute RoPE embeddings (nanochat style)
        self.rotary_seq_len = config.block_size * 10
        head_dim = config.n_embd // config.n_head
        cos, sin = self._precompute_rotary_embeddings(self.rotary_seq_len, head_dim)
        self.register_buffer("cos", cos, persistent=False)
        self.register_buffer("sin", sin, persistent=False)

        # Transformer blocks
        mlp_class = self._get_mlp_class()
        self.blocks = nn.ModuleList([
            TransformerBlock(
                config,
                DenseMLP if (config.first_layer_dense and i == 0) else mlp_class,
                layer_idx=i
            )
            for i in range(config.n_layer)
        ])

        # Output (no bias, nanochat style)
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)

        # NO weight tying (nanochat: untied embeddings)
        # Removed: self.wte.weight = self.lm_head.weight

        # Note: Weight initialization moved to init_weights() method
        # to be called AFTER to_empty() (see nanochat pattern)
        # Do NOT initialize here - to_empty() will discard values!

        # Cast embeddings to bfloat16 (nanochat style)
        self.wte.to(dtype=torch.bfloat16)

        # Report parameters
        n_params = sum(p.numel() for p in self.parameters())
        print(f"Model initialized with {n_params:,} parameters")

        # Report MoE configuration if applicable
        if config.model_type in ["gec", "gec_shared", "gec_shared_capacity", "gec_shared_csr", "ec", "ec_shared", "scattermoe_tc", "tc_shared"]:
            print(f"  MoE Config: G={config.granularity}, E={config.expansion}")
            print(f"  → n_experts={config.n_experts}, expert_dim={config.expert_dim}")
            if config.model_type == "ec":
                chunk_info = f"routing_chunk_seqs={config.routing_chunk_seqs}" if config.routing_chunk_seqs is not None else "global routing"
                print(f"  → Token selection: k = chunk_tokens // {config.expansion} ({chunk_info})")
            elif config.model_type == "scattermoe_tc":
                print(f"  → Token selection: top_k = {config.granularity} (token-choice)")
            elif config.model_type == "tc_shared":
                n_routed = config.n_experts - 1
                print(f"  → {n_routed} routed experts, top_k = {config.granularity - 1} (token-choice)")
                print(f"  → 1 shared expert (always active, dim={config.shared_expert_dim})")
            elif config.model_type in ["gec_shared", "gec_shared_capacity", "gec_shared_csr", "ec_shared"]:
                n_routed = config.n_experts - 1
                active_routed = config.granularity - 1
                print(f"  → {n_routed} routed experts, ~{active_routed} active per token")
                print(f"  → 1 shared expert (always active, dim={config.shared_expert_dim})")
                chunk_info = f"routing_chunk_seqs={config.routing_chunk_seqs}" if config.routing_chunk_seqs is not None else "global routing"
                print(f"  → Token selection: k = chunk_tokens × {active_routed} // ({n_routed} * {config.expansion}) ({chunk_info})")
            else:
                print(f"  → Token selection: k = n_tokens // {config.expansion}")
                print(f"  → Compute-matching: ~{config.expansion} experts, each processes ~1/{config.expansion} of tokens")
    
    def _get_mlp_class(self) -> type:
        """Get the appropriate MLP class based on config."""
        if self.config.model_type == "dense":
            return DenseMLP
        elif self.config.model_type == "gec":
            from .gec import GECMLP
            return GECMLP
        elif self.config.model_type == "gec_shared":
            from .gec_shared import GECSharedMLP
            return GECSharedMLP
        elif self.config.model_type == "gec_shared_capacity":
            # Legacy config support: treat as gec_shared
            from .gec_shared import GECSharedMLP
            return GECSharedMLP
        elif self.config.model_type == "ec":
            from .ec import ECMLP
            return ECMLP
        elif self.config.model_type == "ec_shared":
            from .ec_shared import ECSharedMLP
            return ECSharedMLP
        elif self.config.model_type == "scattermoe_tc":
            from .scattermoe_tc import ScatterMoETokenChoiceMLP
            return ScatterMoETokenChoiceMLP
        elif self.config.model_type == "tc_shared":
            from .scattermoe_tc import ScatterMoETokenChoiceSharedMLP
            return ScatterMoETokenChoiceSharedMLP
        else:
            raise ValueError(f"Unknown model type: {self.config.model_type}")
    
    def _precompute_rotary_embeddings(self, seq_len, head_dim, base=10000, device=None):
        """Precompute RoPE embeddings (from nanochat)."""
        if device is None:
            device = self.wte.weight.device

        channel_range = torch.arange(0, head_dim, 2, dtype=torch.float32, device=device)
        inv_freq = 1.0 / (base ** (channel_range / head_dim))
        t = torch.arange(seq_len, dtype=torch.float32, device=device)
        freqs = torch.outer(t, inv_freq)
        cos, sin = freqs.cos(), freqs.sin()
        cos, sin = cos.bfloat16(), sin.bfloat16()  # Keep in bfloat16 (nanochat style)
        # Add batch and head dims: (1, seq_len, 1, head_dim//2)
        # Shape matches nanochat for broadcasting with (B, T, n_head, head_dim//2)
        cos = cos[None, :, None, :]
        sin = sin[None, :, None, :]

        return cos, sin

    def init_weights(self):
        """Initialize model weights (call AFTER to_empty).

        This follows nanochat's pattern:
        1. Create model on meta device
        2. to_empty(device) to allocate uninitialized tensors
        3. init_weights() to actually initialize them

        Critical: Must be called after to_empty(), not in __init__!

        Uses property-based initialization: all parameters initialized based on
        their dimensions and properties, with verification to ensure completeness.
        """
        # Verify we're not on meta device
        device = self.wte.weight.device
        assert device.type != 'meta', \
            "init_weights() called on meta device! Call to_empty(device) first."

        # Track initialized parameters for verification
        initialized = set()

        # Initialize all parameters based on properties
        for name, param in self.named_parameters():
            # 1. Embeddings (special: std=1.0)
            if 'wte.weight' in name or 'wpe.weight' in name:
                torch.nn.init.normal_(param, mean=0.0, std=1.0)
                initialized.add(id(param))

            # 2. Output projections (zero init, critical for Muon)
            # Includes: lm_head, c_proj, expert_weight2, shared_weight2
            elif 'lm_head.weight' in name or 'c_proj.weight' in name or 'weight2' in name:
                torch.nn.init.zeros_(param)
                initialized.add(id(param))

            # 3. Router (small init for symmetry breaking)
            elif 'router.weight' in name:
                std = 1.0 / math.sqrt(param.shape[1])  # 1/√fan_in
                torch.nn.init.normal_(param, mean=0.0, std=std)
                initialized.add(id(param))

            # 4. All other weight matrices (dimension-based fan-in/fan-out scaling)
            elif 'weight' in name:
                if param.dim() == 2:
                    # Standard 2D weight matrix (fan_out, fan_in)
                    fan_out, fan_in = param.shape[0], param.shape[1]
                elif param.dim() == 3:
                    # Expert weights: (n_experts, fan_out, fan_in)
                    fan_out, fan_in = param.shape[1], param.shape[2]
                else:
                    raise RuntimeError(f"Unexpected weight dimension: {name} has shape {param.shape}")

                # Aspect-ratio scaled Kaiming initialization (nanochat style)
                std = 1.0 / math.sqrt(fan_in) * min(1.0, math.sqrt(fan_out / fan_in))
                torch.nn.init.normal_(param, mean=0.0, std=std)
                initialized.add(id(param))

            # 5. Biases (shouldn't exist in nanochat style, but handle just in case)
            elif 'bias' in name:
                torch.nn.init.zeros_(param)
                initialized.add(id(param))

            else:
                raise RuntimeError(f"Unhandled parameter: {name} (shape: {param.shape})")

        # Verify all parameters were initialized
        all_params = set(id(p) for p in self.parameters())
        if initialized != all_params:
            missing = len(all_params - initialized)
            raise RuntimeError(f"Initialization incomplete: {missing} parameters not initialized!")

        # Reinitialize RoPE embeddings on actual device
        head_dim = self.config.n_embd // self.config.n_head
        cos, sin = self._precompute_rotary_embeddings(
            self.rotary_seq_len, head_dim, device=device
        )
        self.cos.copy_(cos)
        self.sin.copy_(sin)

        # Verify zero-init actually worked
        lm_head_norm = self.lm_head.weight.norm().item()
        assert lm_head_norm < 1e-6, \
            f"lm_head should be zero-initialized, got norm={lm_head_norm}"

        print(f"Weights initialized on {device}")

    def step_complete(
        self,
        step: int,
        ema_start_steps: int,
        threshold_warmup_steps: int,
        threshold_capable: bool,
    ):
        """Complete training step operations.

        Args:
            step: Current training step number
            ema_start_steps: Step where cutoff EMA updates begin
            threshold_warmup_steps: Warmup steps from config (-1 if disabled)
            threshold_capable: Whether current model type supports threshold warmup flow

        This method should be called at the end of each training step (after optimizer.step()).

        Applies delayed cutoff EMA updates at step boundaries and, once threshold
        routing is active, synchronizes cutoff EMAs across all GPUs using a single
        batched collective to avoid rank divergence and deadlock.
        """
        import torch.distributed as dist

        # Finalize accumulation (no collectives, safe per-block).
        # Before ema_start_steps, clear accumulation without updating EMA.
        apply_cutoff_update = threshold_capable and step >= ema_start_steps
        for block in self.blocks:
            finalize_fn = getattr(block.mlp, 'finalize_cutoff_accumulation', None)
            if callable(finalize_fn):
                try:
                    finalize_fn(apply_update=apply_cutoff_update)
                except TypeError:
                    finalize_fn()
            finalize_bias_fn = getattr(block.mlp, 'finalize_bias_update', None)
            if callable(finalize_bias_fn):
                finalize_bias_fn()

        # Sync all cutoff EMAs in a single collective (threshold mode only)
        should_sync = threshold_capable and threshold_warmup_steps >= 0 and step >= threshold_warmup_steps
        if should_sync and dist.is_initialized() and dist.get_world_size() > 1:
            # Explicit barrier before sync to ensure all ranks reach here together
            dist.barrier()

            with torch.no_grad():
                # Collect all raw cutoff EMA buffers from all blocks
                all_emas = []
                block_indices = []  # Track which blocks have syncable cutoff state

                for i, block in enumerate(self.blocks):
                    sync_fn = getattr(block.mlp, 'sync_cutoff_state', None)
                    if callable(sync_fn):
                        ema_tensor = sync_fn()
                    elif hasattr(block.mlp, 'cutoff_ema_raw'):
                        ema_tensor = block.mlp.cutoff_ema_raw
                    elif hasattr(block.mlp, 'cutoff_ema'):
                        ema_tensor = block.mlp.cutoff_ema
                    else:
                        continue

                    # Convert to CPU FP32 for safe gathering
                    ema_cpu = ema_tensor.detach().to(dtype=torch.float32, device='cpu')
                    all_emas.append(ema_cpu)
                    block_indices.append(i)

                if all_emas:
                    # Single all_gather_object for ALL blocks at once
                    payload = all_emas
                    gathered = [None for _ in range(dist.get_world_size())]
                    dist.all_gather_object(gathered, payload)

                    # Average and copy back to original locations
                    for idx, block_idx in enumerate(block_indices):
                        block = self.blocks[block_idx]

                        # Average cutoff EMA buffer across all ranks
                        ema_stack = torch.stack([g[idx] for g in gathered], dim=0)
                        ema_mean = ema_stack.mean(dim=0)
                        sync_fn = getattr(block.mlp, 'sync_cutoff_state', None)
                        if callable(sync_fn):
                            target = sync_fn()
                        elif hasattr(block.mlp, 'cutoff_ema_raw'):
                            target = block.mlp.cutoff_ema_raw
                        elif hasattr(block.mlp, 'cutoff_ema'):
                            target = block.mlp.cutoff_ema
                        else:
                            continue
                        target.copy_(ema_mean.to(dtype=target.dtype, device=target.device))

    def set_routing_mode(self, mode: str):
        """Set routing mode for all MLP layers.

        Args:
            mode: Routing mode ('topk' or 'threshold')
        """
        assert mode in ['topk', 'threshold'], \
            f"mode must be 'topk' or 'threshold', got {mode}"

        for block in self.blocks:
            if hasattr(block.mlp, 'routing_mode'):
                block.mlp.routing_mode = mode

    def _is_ep_distributed(self) -> bool:
        """Return True if running expert-parallel distributed execution."""
        import torch.distributed as dist
        return (
            bool(getattr(self.config, "expert_parallel", False))
            and dist.is_initialized()
            and dist.get_world_size() > 1
        )

    @torch.no_grad()
    def _prepare_ep_eval_inputs(
        self, input_ids: torch.Tensor, pad_token_id: int
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Align local eval input to global max (B, T) for EP collectives."""
        import torch.distributed as dist

        if input_ids.ndim != 2:
            raise ValueError(f"input_ids must have shape (B, T), got {tuple(input_ids.shape)}")

        device = input_ids.device
        dtype = input_ids.dtype
        assert dtype == torch.long, f"input_ids must be torch.long, got {dtype}"

        b_local = input_ids.size(0)
        t_local = input_ids.size(1)
        has_real_rows = b_local > 0 and t_local > 0

        if not has_real_rows:
            input_exec = torch.full(
                (1, 1),
                pad_token_id,
                dtype=torch.long,
                device=device,
            )
            valid_rows = torch.zeros(1, device=device, dtype=torch.bool)
            b_local = 1
            t_local = 1
        else:
            input_exec = input_ids
            valid_rows = torch.ones(b_local, device=device, dtype=torch.bool)

        shape = torch.tensor([b_local, t_local], device=device, dtype=torch.long)
        dist.all_reduce(shape, op=dist.ReduceOp.MAX)
        b_exec, t_exec = int(shape[0].item()), int(shape[1].item())

        if input_exec.size(1) != t_exec:
            seq_padded = torch.full(
                (input_exec.size(0), t_exec),
                pad_token_id,
                device=device,
                dtype=input_exec.dtype,
            )
            seq_padded[:, :input_exec.size(1)] = input_exec
            input_exec = seq_padded

        if input_exec.size(0) != b_exec:
            batch_padded = torch.full(
                (b_exec, input_exec.size(1)),
                pad_token_id,
                device=device,
                dtype=input_exec.dtype,
            )
            batch_padded[:input_exec.size(0)] = input_exec
            input_exec = batch_padded

            valid_padded = torch.zeros(b_exec, device=device, dtype=torch.bool)
            valid_padded[:valid_rows.size(0)] = valid_rows
            valid_rows = valid_padded

        return input_exec, valid_rows

    @torch.no_grad()
    def forward_eval_batch(
        self, input_ids: torch.Tensor, pad_token_id: int = 0
    ) -> EvalBatchForwardResult:
        """Forward helper for eval scoring on prefilled batches."""
        if input_ids.ndim != 2:
            raise ValueError(f"input_ids must have shape (B, T), got {tuple(input_ids.shape)}")
        if input_ids.dtype != torch.long:
            raise ValueError(f"input_ids must be torch.long, got {input_ids.dtype}")

        if self._is_ep_distributed():
            input_exec, valid_rows = self._prepare_ep_eval_inputs(input_ids, pad_token_id)
        else:
            if input_ids.numel() == 0:
                raise ValueError("input_ids cannot be empty when EP distributed mode is disabled")
            input_exec = input_ids
            valid_rows = torch.ones(input_exec.size(0), device=input_exec.device, dtype=torch.bool)

        logits = self(input_exec).logits
        batch_size, seq_len = input_exec.size()
        target_ids = torch.roll(input_exec, shifts=-1, dims=1)
        losses = F.cross_entropy(
            logits.view(batch_size * seq_len, -1),
            target_ids.view(batch_size * seq_len),
            reduction="none",
        ).view(batch_size, seq_len)
        losses[:, -1] = float("nan")
        predictions = logits.argmax(dim=-1)

        return EvalBatchForwardResult(
            losses=losses,
            predictions=predictions,
            valid_rows=valid_rows,
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        labels: Optional[torch.Tensor] = None
    ) -> ModelOutput:
        """
        Forward pass with unified interface.

        Args:
            input_ids: Input token IDs of shape (B, T)
            labels: Target token IDs of shape (B, T) for loss computation

        Returns:
            ModelOutput with logits, loss (if labels provided), and metrics
        """
        device = input_ids.device
        B, T = input_ids.size()
        assert T <= self.config.block_size, \
            f"Sequence length {T} exceeds block size {self.config.block_size}"

        # Token embeddings only (no positional! - nanochat style)
        x = self.wte(input_ids)
        x = norm(x)  # Norm after embedding (nanochat style)

        # Get RoPE for current sequence (slice at dim=1 for seq_len, nanochat style)
        cos_sin = self.cos[:, :T], self.sin[:, :T]

        # Forward through blocks
        all_metrics = {}
        aux_loss_total = None
        layer_data = {} if not self.training else None  # Collect layer data during eval
        repr_layers = {0, self.config.n_layer // 2, self.config.n_layer - 1}

        for i, block in enumerate(self.blocks):
            x, block_metrics = block(x, cos_sin)  # Pass RoPE!

            # Separate layer_data from regular metrics
            if 'layer_data' in block_metrics:
                if layer_data is not None and i in repr_layers:
                    layer_data[i] = block_metrics.pop('layer_data')
                else:
                    block_metrics.pop('layer_data')  # Remove if not needed

            aux_loss = block_metrics.pop('aux_loss', None)
            if aux_loss is not None:
                aux_loss_total = aux_loss if aux_loss_total is None else aux_loss_total + aux_loss

            # Aggregate regular metrics
            for k, v in block_metrics.items():
                if k not in all_metrics:
                    all_metrics[k] = []
                all_metrics[k].append(v)

        # Final norm and output projection (nanochat style: functional norm)
        x = norm(x)
        logits = self.lm_head(x)

        # Logits softcapping (Gemma-style, from nanochat)
        softcap = 15.0
        logits = softcap * torch.tanh(logits / softcap)

        # Compute loss if labels provided
        loss = None
        if labels is not None:
            loss = F.cross_entropy(
                logits.view(-1, logits.size(-1)),
                labels.view(-1)
            )
            if self.training and aux_loss_total is not None and self.config.aux_loss_coef > 0:
                aux_term = self.config.aux_loss_coef * aux_loss_total
                # Keep loss value as CE for logging, but include aux gradients.
                loss = loss + aux_term - aux_term.detach()

        # Aggregate metrics across layers
        aggregated_metrics = {}
        for k, v_list in all_metrics.items():
            if v_list:
                # Assert: All metrics from layers should be tensors
                assert all(torch.is_tensor(v) for v in v_list), \
                    f"Metric '{k}' contains non-tensor values from layers"
                aggregated_metrics[k] = torch.stack(v_list).mean(dim=0)

        if aux_loss_total is not None:
            aggregated_metrics["aux_loss"] = aux_loss_total.detach()

        # Convert metrics to Python types to prevent distributed deadlocks
        scalar_metrics = self._metrics_to_scalars(aggregated_metrics)

        # Assert: No tensors in output
        assert not any(torch.is_tensor(v) for v in scalar_metrics.values()), \
            "BUG: Tensors leaked through _metrics_to_scalars()"

        return ModelOutput(
            logits=logits,
            loss=loss,
            metrics=scalar_metrics,
            layer_data=layer_data if layer_data else None
        )

    @staticmethod
    def _metrics_to_scalars(metrics: dict) -> dict:
        """
        Convert tensor metrics to Python types.

        CRITICAL: This prevents distributed deadlocks by ensuring tensors
        never reach rank-divergent code in the training loop.

        Called in forward() so training loop only handles Python scalars/lists.

        Args:
            metrics: Dictionary of tensor metrics

        Returns:
            Dictionary of Python primitives (float/list)
        """
        result = {}
        for k, v in metrics.items():
            # Assert: Input should be tensors
            assert torch.is_tensor(v), \
                f"Metric '{k}' is not a tensor (got {type(v)}). " \
                f"This indicates a bug in metric computation."

            # Convert: GPU tensor → CPU tensor → Python type
            v_cpu = v.detach().cpu()

            if v_cpu.numel() == 1:
                # Scalar metric
                result[k] = float(v_cpu.item())
            else:
                # Vector metric
                result[k] = v_cpu.tolist()

        return result

    def generate(
        self,
        idx: torch.Tensor,
        max_new_tokens: int,
        temperature: float = 1.0,
        top_k: Optional[int] = None
    ) -> torch.Tensor:
        """Generate tokens autoregressively."""
        for _ in range(max_new_tokens):
            # Crop context if needed
            idx_cond = idx if idx.size(1) <= self.config.block_size else \
                       idx[:, -self.config.block_size:]
            
            # Forward pass
            output = self(idx_cond)
            logits = output.logits[:, -1, :] / temperature
            
            # Apply top-k filtering
            if top_k is not None:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = -float('Inf')
            
            # Sample
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)
        
        return idx 
