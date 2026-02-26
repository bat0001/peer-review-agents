"""Main benchmark script for comparing Dense vs GEC MLP performance."""

import argparse
import importlib.util
import os
import sys
from typing import Any, Dict, List, Tuple

import torch
import torch.nn as nn

# Add project root to the path when running as a script and support relative imports.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE_DIR = os.path.dirname(__file__)

if not __package__:
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)
    # Populate sibling modules via importlib to mimic package imports.
    for name in ('timing_utils', 'flop_counter', 'validation'):
        spec = importlib.util.spec_from_file_location(f'benchmark.mlp.{name}', os.path.join(MODULE_DIR, f'{name}.py'))
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        sys.modules[f'benchmark.mlp.{name}'] = module
    __package__ = 'benchmark.mlp'


def detect_gpu() -> str:
    """Auto-detect GPU type from supported list."""
    gpu_name = torch.cuda.get_device_name(0).upper()
    
    if "H100" in gpu_name:
        return "H100"
    elif "A100" in gpu_name:
        return "A100"
    elif "A5000" in gpu_name or "RTX A5000" in gpu_name:
        return "A5000"
    elif "4090" in gpu_name or "RTX 4090" in gpu_name:
        return "4090"
    else:
        print(f"Unsupported GPU: {gpu_name}")
        print("Supported GPUs: H100, A100, A5000, RTX 4090")
        sys.exit(1)

from src.models.model_base import DenseMLP, ModelConfig
from src.models.gec import GECMLP
from .timing_utils import (
    benchmark_forward_backward,
    measure_memory_usage,
    print_benchmark_results,
)
from .flop_counter import (
    compare_flop_efficiency,
    count_dense_mlp_flops,
    count_gec_mlp_flops,
    print_flop_analysis,
)
from .validation import run_validation_test


def create_test_config(
    batch_size: int = 32,
    seq_len: int = 1024,
    n_embd: int = 768,
    n_experts: int = 16,
    expert_dim: int = None,
    density: float = 0.125
) -> ModelConfig:
    """Create a test configuration based on actual model configs."""
    config = ModelConfig(
        n_embd=n_embd,
        n_experts=n_experts,
        expert_dim=expert_dim or (2 * n_embd),  # Default to 2x like in gec.yaml
        density=density
    )
    return config


def benchmark_mlp_layer(
    mlp: nn.Module,
    input_tensor: torch.Tensor,
    name: str,
    num_runs: int = 50,
    warmup_runs: int = 5,
    with_compile: bool = False
) -> Dict[str, Any]:
    """
    Benchmark a single MLP layer.
    
    Args:
        mlp: MLP module to benchmark
        input_tensor: Input tensor
        name: Name for the benchmark
        num_runs: Number of timing runs
        warmup_runs: Number of warmup runs
        with_compile: Whether to use torch.compile
    
    Returns:
        Benchmark results
    """
    # Optionally compile the model
    if with_compile:
        print(f"Compiling {name}...")
        mlp = torch.compile(mlp)
        name = f"{name}_compiled"
    
    # Move to GPU
    mlp = mlp.cuda()
    input_tensor = input_tensor.cuda()
    
    # Benchmark forward/backward passes
    timing_results = benchmark_forward_backward(
        mlp, input_tensor, name=name, 
        num_runs=num_runs, warmup_runs=warmup_runs
    )
    
    # Measure memory usage
    def forward_fn(x):
        with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
            output = mlp(x)
            if isinstance(output, tuple):
                return output[0]
            return output
    
    memory_results = measure_memory_usage(forward_fn, (input_tensor,))
    
    return {
        'timing': timing_results,
        'memory': memory_results,
        'name': name
    }


def run_comparison_benchmark(
    batch_size: int = 32,
    seq_len: int = 1024, 
    n_embd: int = 768,
    n_experts: int = 16,
    expert_dim: int = None,
    density: float = 0.125,
    num_runs: int = 50,
    warmup_runs: int = 5,
    with_compile: bool = False,
    gpu: str = "A5000",
    validate: bool = True,
    validation_only: bool = False
) -> Dict[str, Any]:
    """
    Run a complete comparison benchmark between Dense and GEC MLPs.
    
    Args:
        batch_size: Batch size
        seq_len: Sequence length
        n_embd: Embedding dimension
        n_experts: Number of experts for GEC
        expert_dim: Expert hidden dimension (defaults to n_embd)
        density: Expert density for GEC
        num_runs: Number of timing runs
        warmup_runs: Number of warmup runs
        with_compile: Whether to use torch.compile
    
    Returns:
        Complete benchmark results
    """
    expert_dim = expert_dim or (2 * n_embd)
    
    # Run validation if requested
    if validate or validation_only:
        print(f"\n{'='*80}")
        print(f"RUNNING VALIDATION")
        print(f"{'='*80}")
        
        validation_passed = run_validation_test(
            batch_size=batch_size,
            seq_len=seq_len, 
            n_embd=n_embd,
            n_experts=n_experts,
            expert_dim=expert_dim,
            density=density,
            rtol=1e-5,
            atol=1e-6,
            backward_rtol=1e-4,
            backward_atol=1e-5
        )
        
        if not validation_passed:
            print(f"\n{'='*80}")
            print("⚠️  VALIDATION FAILED - Continuing with benchmark")
            print("Note: Current GECMLP produces different results than reference")
            print(f"{'='*80}")
        
        if validation_only:
            return {"validation": "passed" if validation_passed else "failed"}
    
    print(f"\n{'='*80}")
    print(f"BENCHMARKING MLP LAYERS")
    print(f"{'='*80}")
    print(f"GPU: {gpu}")
    print(f"Batch size: {batch_size}, Seq length: {seq_len}, Embedding dim: {n_embd}")
    print(f"GEC: {n_experts} experts, expert_dim: {expert_dim}, density: {density}")
    print(f"Runs: {num_runs}, Warmup: {warmup_runs}, Compile: {with_compile}")
    
    # Create configurations
    config = create_test_config(batch_size, seq_len, n_embd, n_experts, expert_dim, density)
    
    # Create models
    dense_mlp = DenseMLP(config)
    gec_mlp = GECMLP(config)
    
    # Create input tensor
    input_tensor = torch.randn(batch_size, seq_len, n_embd)
    
    print(f"\nModel Parameters:")
    dense_params = sum(p.numel() for p in dense_mlp.parameters())
    gec_params = sum(p.numel() for p in gec_mlp.parameters())
    print(f"Dense MLP: {dense_params:,} parameters")
    print(f"GEC MLP:   {gec_params:,} parameters ({gec_params/dense_params:.2f}x)")
    
    # Benchmark both models
    dense_results = benchmark_mlp_layer(
        dense_mlp, input_tensor, "Dense_MLP", 
        num_runs, warmup_runs, with_compile
    )
    
    gec_results = benchmark_mlp_layer(
        gec_mlp, input_tensor, "GEC_MLP",
        num_runs, warmup_runs, with_compile
    )
    
    # Calculate FLOP counts
    dense_flops = count_dense_mlp_flops(batch_size, seq_len, n_embd)
    gec_flops = count_gec_mlp_flops(batch_size, seq_len, n_embd, n_experts, expert_dim, density)
    
    # Get timing results for efficiency calculation
    dense_forward_time = dense_results['timing']['forward']['mean']
    gec_forward_time = gec_results['timing']['forward']['mean']
    
    # Compare FLOP efficiency
    flop_comparison = compare_flop_efficiency(
        dense_flops, gec_flops, dense_forward_time, gec_forward_time, gpu
    )
    
    return {
        'config': {
            'batch_size': batch_size,
            'seq_len': seq_len,
            'n_embd': n_embd,
            'n_experts': n_experts,
            'expert_dim': expert_dim,
            'density': density,
            'with_compile': with_compile,
            'gpu': gpu
        },
        'dense_results': dense_results,
        'gec_results': gec_results,
        'dense_flops': dense_flops,
        'gec_flops': gec_flops,
        'flop_comparison': flop_comparison,
        'parameter_counts': {
            'dense': dense_params,
            'gec': gec_params
        }
    }


def print_complete_results(results: Dict[str, Any]):
    """Print complete benchmark results."""
    # Print timing results
    print_benchmark_results(results['dense_results']['timing'], "Dense MLP Timing")
    print_benchmark_results(results['gec_results']['timing'], "GEC MLP Timing") 
    
    # Print memory results
    print(f"\nMEMORY USAGE:")
    print(f"Dense MLP: {results['dense_results']['memory']['peak_memory_mb']:.2f} MB")
    print(f"GEC MLP:   {results['gec_results']['memory']['peak_memory_mb']:.2f} MB")
    
    # Print FLOP analysis
    print_flop_analysis(
        results['dense_flops'],
        results['gec_flops'], 
        results['flop_comparison']
    )
    
    # Print summary
    dense_forward = results['dense_results']['timing']['forward']['mean'] * 1000
    gec_forward = results['gec_results']['timing']['forward']['mean'] * 1000
    speedup = dense_forward / gec_forward
    
    print(f"\nSUMMARY:")
    print(f"Dense Forward: {dense_forward:.3f} ms")
    print(f"GEC Forward:   {gec_forward:.3f} ms")
    print(f"Speedup:       {speedup:.2f}x ({'faster' if speedup > 1 else 'slower'})")


def run_scaling_analysis(
    base_config: Dict[str, Any],
    scaling_params: List[Tuple[str, List[Any]]],
    with_compile: bool = False
):
    """
    Run scaling analysis across different parameters.
    
    Args:
        base_config: Base configuration dictionary
        scaling_params: List of (param_name, values) tuples to scale
        with_compile: Whether to use torch.compile
    """
    print(f"\n{'='*80}")
    print(f"SCALING ANALYSIS")
    print(f"{'='*80}")
    
    for param_name, values in scaling_params:
        print(f"\nScaling {param_name}: {values}")
        print(f"{'='*60}")
        
        results_summary = []
        
        for value in values:
            config = base_config.copy()
            config[param_name] = value
            config['with_compile'] = with_compile
            
            try:
                results = run_comparison_benchmark(**config)
                
                dense_time = results['dense_results']['timing']['forward']['mean'] * 1000
                gec_time = results['gec_results']['timing']['forward']['mean'] * 1000
                speedup = dense_time / gec_time
                efficiency_ratio = results['flop_comparison']['efficiency_ratio']
                
                results_summary.append({
                    param_name: value,
                    'dense_ms': dense_time,
                    'gec_ms': gec_time,
                    'speedup': speedup,
                    'efficiency_ratio': efficiency_ratio
                })
                
                print(f"{param_name}={value}: Dense={dense_time:.2f}ms, GEC={gec_time:.2f}ms, "
                      f"Speedup={speedup:.2f}x, Efficiency={efficiency_ratio:.2f}x")
                
            except Exception as e:
                print(f"{param_name}={value}: ERROR - {e}")
        
        # Print summary table
        if results_summary:
            print(f"\n{param_name.upper()} SCALING SUMMARY:")
            print(f"{'Value':<10} {'Dense (ms)':<12} {'GEC (ms)':<10} {'Speedup':<8} {'Efficiency':<10}")
            print(f"{'-'*60}")
            for r in results_summary:
                print(f"{r[param_name]:<10} {r['dense_ms']:<12.2f} {r['gec_ms']:<10.2f} "
                      f"{r['speedup']:<8.2f} {r['efficiency_ratio']:<10.2f}")


def main():
    """Main benchmark script."""
    parser = argparse.ArgumentParser(description="Benchmark Dense vs GEC MLP performance")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--seq-len", type=int, default=1024, help="Sequence length")
    parser.add_argument("--n-embd", type=int, default=768, help="Embedding dimension")
    parser.add_argument("--n-experts", type=int, default=16, help="Number of experts")
    parser.add_argument("--expert-dim", type=int, help="Expert hidden dimension (default: 2*n_embd)")
    parser.add_argument("--density", type=float, default=0.125, help="Expert density")
    parser.add_argument("--runs", type=int, default=50, help="Number of timing runs")
    parser.add_argument("--warmup", type=int, default=5, help="Number of warmup runs")
    parser.add_argument("--compile", action="store_true", help="Use torch.compile")
    parser.add_argument("--scaling", action="store_true", help="Run scaling analysis")
    parser.add_argument("--gpu", type=str, choices=["A5000", "H100", "A100", "4090"], help="GPU type for FLOP calculations (auto-detected if not specified)")
    parser.add_argument("--no-validate", action="store_true", help="Skip validation before benchmarking")
    parser.add_argument("--validate-only", action="store_true", help="Run validation only (skip performance benchmark)")
    
    args = parser.parse_args()
    
    # Auto-detect GPU if not specified
    if args.gpu is None:
        args.gpu = detect_gpu()
        print(f"Auto-detected GPU: {args.gpu}")
    
    if args.scaling:
        base_config = {
            'batch_size': args.batch_size,
            'seq_len': args.seq_len,
            'n_embd': args.n_embd,
            'n_experts': args.n_experts,
            'expert_dim': args.expert_dim,
            'density': args.density,
            'num_runs': args.runs,
            'warmup_runs': args.warmup,
            'gpu': args.gpu
        }
        
        scaling_params = [
            ('batch_size', [8, 16, 32, 64]),
            ('seq_len', [256, 512, 1024, 2048]),
            ('n_experts', [4, 8, 16, 32]),
            ('density', [0.0625, 0.125, 0.25, 0.5])
        ]
        
        run_scaling_analysis(base_config, scaling_params, args.compile)
    else:
        # Single benchmark
        results = run_comparison_benchmark(
            batch_size=args.batch_size,
            seq_len=args.seq_len,
            n_embd=args.n_embd,
            n_experts=args.n_experts,
            expert_dim=args.expert_dim,
            density=args.density,
            num_runs=args.runs,
            warmup_runs=args.warmup,
            with_compile=args.compile,
            gpu=args.gpu,
            validate=not args.no_validate,
            validation_only=args.validate_only
        )
        
        if args.validate_only:
            if results.get("validation") == "passed":
                print("✅ Validation completed successfully!")
            else:
                print("⚠️  Validation completed with differences!")
            return
        
        print_complete_results(results)


if __name__ == "__main__":
    main()
