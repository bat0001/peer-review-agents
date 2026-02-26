"""FLOP counting utilities for MLP implementations."""

import torch
import torch.nn as nn
from typing import Dict, Any, Tuple
from src.models.model_base import ModelConfig


def count_dense_mlp_flops(batch_size: int, seq_len: int, n_embd: int) -> Dict[str, int]:
    """
    Count FLOPs for a standard dense MLP.
    
    Dense MLP structure:
    - Linear: n_embd -> 4*n_embd 
    - GELU activation
    - Linear: 4*n_embd -> n_embd
    
    Args:
        batch_size: Batch size
        seq_len: Sequence length
        n_embd: Embedding dimension
    
    Returns:
        Dictionary with FLOP counts
    """
    n_tokens = batch_size * seq_len
    
    # First linear layer: (B*T, n_embd) @ (n_embd, 4*n_embd)
    linear1_flops = n_tokens * n_embd * (4 * n_embd)
    
    # GELU approximation (assuming ~3 ops per element for GELU)
    gelu_flops = n_tokens * (4 * n_embd) * 3
    
    # Second linear layer: (B*T, 4*n_embd) @ (4*n_embd, n_embd)
    linear2_flops = n_tokens * (4 * n_embd) * n_embd
    
    total_flops = linear1_flops + gelu_flops + linear2_flops
    
    return {
        'linear1_flops': linear1_flops,
        'activation_flops': gelu_flops,
        'linear2_flops': linear2_flops,
        'total_flops': total_flops,
        'tokens': n_tokens
    }


def count_gec_mlp_flops(
    batch_size: int, 
    seq_len: int, 
    n_embd: int, 
    n_experts: int,
    expert_dim: int,
    density: float
) -> Dict[str, int]:
    """
    Count FLOPs for GEC MLP.
    
    GEC MLP operations:
    1. Router computation: (B*T, n_embd) @ (n_embd, n_experts)
    2. Sigmoid activation for router
    3. Top-k selection per expert 
    4. Expert computation for selected tokens
    5. Scatter-add for output accumulation
    
    Args:
        batch_size: Batch size
        seq_len: Sequence length
        n_embd: Embedding dimension
        n_experts: Number of experts
        expert_dim: Expert hidden dimension
        density: Fraction of tokens each expert processes
    
    Returns:
        Dictionary with FLOP counts
    """
    n_tokens = batch_size * seq_len
    tokens_per_expert = int(n_tokens * density)
    
    # Router computation: (B*T, n_embd) @ (n_embd, n_experts)
    router_flops = n_tokens * n_embd * n_experts
    
    # Sigmoid activation
    sigmoid_flops = n_tokens * n_experts * 2  # exp + division
    
    # Top-k selection (approximate - depends on implementation)
    # This is a rough estimate for the sorting/selection overhead
    topk_flops = n_experts * n_tokens * 4  # Rough estimate for topk ops
    
    # Expert computation - each expert processes tokens_per_expert tokens
    total_expert_tokens = n_experts * tokens_per_expert
    
    # First expert layer: (tokens_per_expert, n_embd) @ (n_embd, expert_dim) per expert
    expert_linear1_flops = total_expert_tokens * n_embd * expert_dim
    
    # GELU activation
    expert_gelu_flops = total_expert_tokens * expert_dim * 3
    
    # Second expert layer: (tokens_per_expert, expert_dim) @ (expert_dim, n_embd) per expert
    expert_linear2_flops = total_expert_tokens * expert_dim * n_embd
    
    # Weight application (router probabilities)
    weight_flops = total_expert_tokens * n_embd
    
    # Scatter-add operations (approximate)
    scatter_flops = total_expert_tokens * n_embd
    
    total_flops = (router_flops + sigmoid_flops + topk_flops + 
                   expert_linear1_flops + expert_gelu_flops + 
                   expert_linear2_flops + weight_flops + scatter_flops)
    
    return {
        'router_flops': router_flops,
        'sigmoid_flops': sigmoid_flops,
        'topk_flops': topk_flops,
        'expert_linear1_flops': expert_linear1_flops,
        'expert_activation_flops': expert_gelu_flops,
        'expert_linear2_flops': expert_linear2_flops,
        'weight_flops': weight_flops,
        'scatter_flops': scatter_flops,
        'total_flops': total_flops,
        'tokens': n_tokens,
        'expert_tokens': total_expert_tokens,
        'tokens_per_expert': tokens_per_expert,
        'density': density
    }


def compute_flop_efficiency(flops: int, time_seconds: float, gpu: str = "A5000") -> Dict[str, float]:
    """
    Compute FLOP efficiency metrics.
    
    Args:
        flops: Number of floating point operations
        time_seconds: Time taken in seconds
        gpu: GPU type for peak performance reference
    
    Returns:
        Dictionary with efficiency metrics
    """
    tflops_per_second = (flops / time_seconds) / 1e12
    
    # Peak TFLOPS for BF16 tensor operations (non-sparse)
    gpu_peak_tflops = {
        "H100": 1000,   # BF16 non-sparse
        "A100": 312,    # BF16 non-sparse
        "A5000": 111,   # BF16 non-sparse
        "4090": 165     # BF16 non-sparse
    }
    
    peak_tflops = gpu_peak_tflops.get(gpu, 111)
    utilization_percent = (tflops_per_second / peak_tflops) * 100
    
    return {
        'tflops_per_second': tflops_per_second,
        'utilization_percent': utilization_percent
    }


def compare_flop_efficiency(
    dense_flops: Dict[str, int],
    gec_flops: Dict[str, int], 
    dense_time: float,
    gec_time: float,
    gpu: str = "A5000"
) -> Dict[str, Any]:
    """
    Compare FLOP efficiency between dense and GEC MLPs.
    
    Args:
        dense_flops: FLOP counts for dense MLP
        gec_flops: FLOP counts for GEC MLP  
        dense_time: Time for dense MLP (seconds)
        gec_time: Time for GEC MLP (seconds)
    
    Returns:
        Comparison metrics
    """
    dense_efficiency = compute_flop_efficiency(dense_flops['total_flops'], dense_time, gpu)
    gec_efficiency = compute_flop_efficiency(gec_flops['total_flops'], gec_time, gpu)
    
    flop_ratio = gec_flops['total_flops'] / dense_flops['total_flops']
    time_ratio = gec_time / dense_time
    efficiency_ratio = gec_efficiency['tflops_per_second'] / dense_efficiency['tflops_per_second']
    
    return {
        'dense_tflops_per_sec': dense_efficiency['tflops_per_second'],
        'gec_tflops_per_sec': gec_efficiency['tflops_per_second'],
        'dense_utilization': dense_efficiency['utilization_percent'],
        'gec_utilization': gec_efficiency['utilization_percent'],
        'flop_ratio': flop_ratio,
        'time_ratio': time_ratio,
        'efficiency_ratio': efficiency_ratio,
        'efficiency_gap': (1.0 - efficiency_ratio) * 100,  # Percent efficiency loss
        'theoretical_speedup': flop_ratio,  # If GEC matched dense efficiency
        'actual_speedup': 1.0 / time_ratio
    }


def print_flop_analysis(
    dense_flops: Dict[str, int],
    gec_flops: Dict[str, int],
    comparison: Dict[str, Any]
):
    """Pretty print FLOP analysis results."""
    print(f"\n{'='*80}")
    print(f"{'FLOP ANALYSIS':^80}")
    print(f"{'='*80}")
    
    print(f"\nDENSE MLP:")
    print(f"  Linear 1:    {dense_flops['linear1_flops']:,} FLOPs")
    print(f"  Activation:  {dense_flops['activation_flops']:,} FLOPs")
    print(f"  Linear 2:    {dense_flops['linear2_flops']:,} FLOPs")
    print(f"  Total:       {dense_flops['total_flops']:,} FLOPs")
    
    print(f"\nGEC MLP:")
    print(f"  Router:      {gec_flops['router_flops']:,} FLOPs")
    print(f"  Sigmoid:     {gec_flops['sigmoid_flops']:,} FLOPs") 
    print(f"  Top-K:       {gec_flops['topk_flops']:,} FLOPs")
    print(f"  Expert L1:   {gec_flops['expert_linear1_flops']:,} FLOPs")
    print(f"  Expert Act:  {gec_flops['expert_activation_flops']:,} FLOPs")
    print(f"  Expert L2:   {gec_flops['expert_linear2_flops']:,} FLOPs")
    print(f"  Weighting:   {gec_flops['weight_flops']:,} FLOPs")
    print(f"  Scatter:     {gec_flops['scatter_flops']:,} FLOPs")
    print(f"  Total:       {gec_flops['total_flops']:,} FLOPs")
    print(f"  Expert Tokens: {gec_flops['expert_tokens']:,} (density: {gec_flops['density']:.2f})")
    
    print(f"\nEFFICIENCY COMPARISON:")
    print(f"  Dense:       {comparison['dense_tflops_per_sec']:.2f} TFLOPS/s ({comparison['dense_utilization']:.1f}% util)")
    print(f"  GEC:         {comparison['gec_tflops_per_sec']:.2f} TFLOPS/s ({comparison['gec_utilization']:.1f}% util)")
    print(f"  FLOP Ratio:  {comparison['flop_ratio']:.2f}x (GEC vs Dense)")
    print(f"  Time Ratio:  {comparison['time_ratio']:.2f}x (GEC vs Dense)")
    print(f"  Efficiency:  {comparison['efficiency_ratio']:.2f}x (GEC vs Dense)")
    print(f"  Efficiency Gap: {comparison['efficiency_gap']:.1f}% loss")
    print(f"  Theoretical Speedup: {comparison['theoretical_speedup']:.2f}x")
    print(f"  Actual Speedup:      {comparison['actual_speedup']:.2f}x")
    
    print(f"{'='*80}")
