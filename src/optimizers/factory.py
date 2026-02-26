"""
Optimizer factory for nanochat-style hybrid optimization.
Creates dual optimizers: Muon for matrices, AdamW for embeddings/lm_head.
For Expert Parallelism (EP), adds a third local optimizer for sharded expert weights.
"""

from typing import Tuple, Union
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
    expert_parallel: bool = False,
) -> Union[Tuple[torch.optim.Optimizer, torch.optim.Optimizer],
           Tuple[torch.optim.Optimizer, torch.optim.Optimizer, torch.optim.Optimizer]]:
    """
    Create nanochat-style hybrid optimizer.

    Parameters split into groups:
    - AdamW: embeddings (wte) and unembedding (lm_head), with different LRs
    - Muon: 2D matrix parameters (transformer blocks)
    - (EP only) Local Muon: expert weights (sharded, no sync)

    Args:
        model: Model to optimize
        unembedding_lr: Learning rate for lm_head (default: 0.004)
        embedding_lr: Learning rate for wte (default: 0.2, 50x higher!)
        matrix_lr: Learning rate for Muon (transformer blocks, default: 0.02)
        weight_decay: Weight decay for AdamW (default: 0.0)
        model_dim: Model embedding dimension for μP-style LR scaling
        use_dist: Whether to use distributed optimizers (DistAdamW, DistMuon)
        expert_parallel: If True, create 3rd optimizer for local expert weights

    Returns:
        (adamw_optimizer, muon_optimizer) tuple, or
        (adamw_optimizer, muon_optimizer, expert_optimizer) tuple if expert_parallel=True
    """
    # Separate parameters by type
    matrix_params = []      # 2D params → Muon
    embedding_params = []   # wte → AdamW
    lm_head_params = []     # lm_head + other → AdamW
    local_expert_params = []  # EP: expert weights → Local Muon (no sync)

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue

        # EP mode: expert weights go to local optimizer (no sync)
        if expert_parallel and 'expert_weight' in name:
            local_expert_params.append(param)
        elif 'wte' in name or 'token_embedding' in name:
            embedding_params.append(param)  # → AdamW, lr=0.2
        elif 'lm_head' in name or "router" in name:
            # According to MuP MoE paper (https://arxiv.org/abs/2508.09752v1), router weights is also "unembedding", so we put it in the same group as lm_head.
            lm_head_params.append(param)  # → AdamW, lr=0.004
        elif param.ndim == 2 or param.ndim == 3:
            matrix_params.append(param)  # → Muon, lr=0.02
        else:
            # 0D/1D params (norms, biases if any) → AdamW
            lm_head_params.append(param)  # → AdamW, lr=0.004

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
    optimizers = [adamw_optimizer, muon_optimizer]

    # EP mode: create local Muon for expert weights (no sync!)
    if expert_parallel and local_expert_params:
        expert_optimizer = Muon(local_expert_params, lr=matrix_lr, momentum=0.95)
        optimizers.append(expert_optimizer)

    for opt in optimizers:
        for group in opt.param_groups:
            group['initial_lr'] = group['lr']

    if expert_parallel and local_expert_params:
        return adamw_optimizer, muon_optimizer, expert_optimizer
    return adamw_optimizer, muon_optimizer
