"""Timing utilities for precise performance measurements."""

import time
import torch
from typing import Callable, Dict, List, Any
import statistics
import gc


class Timer:
    """Context manager for timing operations with CUDA synchronization."""
    
    def __init__(self, name: str = "", warmup: bool = False):
        self.name = name
        self.warmup = warmup
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        torch.cuda.synchronize()
        gc.collect()
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        torch.cuda.synchronize()
        self.end_time = time.perf_counter()
    
    @property
    def elapsed(self) -> float:
        """Return elapsed time in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return self.end_time - self.start_time


def benchmark_function(
    func: Callable,
    inputs: tuple,
    name: str = "",
    num_runs: int = 100,
    warmup_runs: int = 10
) -> Dict[str, float]:
    """
    Benchmark a function with multiple runs and return timing statistics.
    
    Args:
        func: Function to benchmark
        inputs: Tuple of inputs to pass to func
        name: Name for the benchmark
        num_runs: Number of timing runs
        warmup_runs: Number of warmup runs (not timed)
    
    Returns:
        Dictionary with timing statistics
    """
    # Warmup runs
    for _ in range(warmup_runs):
        with Timer(warmup=True):
            _ = func(*inputs)
    
    # Timed runs
    times = []
    for _ in range(num_runs):
        with Timer() as timer:
            _ = func(*inputs)
        times.append(timer.elapsed)
    
    return {
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'std': statistics.stdev(times) if len(times) > 1 else 0.0,
        'min': min(times),
        'max': max(times),
        'runs': num_runs,
        'name': name
    }


def benchmark_forward_backward(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    target: torch.Tensor = None,
    loss_fn: Callable = None,
    name: str = "",
    num_runs: int = 50,
    warmup_runs: int = 5
) -> Dict[str, Dict[str, float]]:
    """
    Benchmark forward and backward passes separately.
    
    Args:
        model: Model to benchmark
        input_tensor: Input tensor
        target: Target tensor for loss computation
        loss_fn: Loss function (if None, uses sum() for backward)
        name: Name for the benchmark
        num_runs: Number of timing runs
        warmup_runs: Number of warmup runs
    
    Returns:
        Dictionary with forward and backward timing statistics
    """
    model.train()
    
    # Always use mixed precision with bfloat16
    amp_context = torch.autocast(device_type='cuda', dtype=torch.bfloat16)
    
    def forward_pass():
        with amp_context:
            output = model(input_tensor)
            if isinstance(output, tuple):
                return output[0]  # Return tensor part
            return output
    
    def backward_pass():
        model.zero_grad()
        with amp_context:
            output = model(input_tensor)
            if isinstance(output, tuple):
                output = output[0]
            
            if target is not None and loss_fn is not None:
                loss = loss_fn(output, target)
            else:
                loss = output.sum()
        
        loss.backward()
    
    # Benchmark forward pass
    forward_stats = benchmark_function(
        forward_pass, (), f"{name}_forward", num_runs, warmup_runs
    )
    
    # Benchmark backward pass  
    backward_stats = benchmark_function(
        backward_pass, (), f"{name}_backward", num_runs, warmup_runs
    )
    
    return {
        'forward': forward_stats,
        'backward': backward_stats
    }


def measure_memory_usage(func: Callable, inputs: tuple) -> Dict[str, float]:
    """
    Measure peak memory usage during function execution.
    
    Args:
        func: Function to measure
        inputs: Inputs to the function
    
    Returns:
        Dictionary with memory statistics in MB
    """
    # Clear cache and reset stats
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    
    # Measure baseline memory
    baseline_memory = torch.cuda.memory_allocated()
    
    # Run function
    _ = func(*inputs)
    
    # Get peak memory usage
    peak_memory = torch.cuda.max_memory_allocated()
    current_memory = torch.cuda.memory_allocated()
    
    return {
        'peak_memory_mb': (peak_memory - baseline_memory) / 1024**2,
        'allocated_memory_mb': (current_memory - baseline_memory) / 1024**2
    }


def print_benchmark_results(results: Dict[str, Any], title: str = "Benchmark Results"):
    """Pretty print benchmark results."""
    print(f"\n{'='*60}")
    print(f"{title:^60}")
    print(f"{'='*60}")
    
    for key, value in results.items():
        if isinstance(value, dict) and 'mean' in value:
            print(f"\n{key.upper()}:")
            print(f"  Mean:   {value['mean']*1000:.3f} ms")
            print(f"  Median: {value['median']*1000:.3f} ms")
            print(f"  Std:    {value['std']*1000:.3f} ms")
            print(f"  Min:    {value['min']*1000:.3f} ms")
            print(f"  Max:    {value['max']*1000:.3f} ms")
            print(f"  Runs:   {value['runs']}")
        elif isinstance(value, dict):
            print(f"\n{key.upper()}:")
            for subkey, subvalue in value.items():
                if isinstance(subvalue, dict) and 'mean' in subvalue:
                    print(f"  {subkey}:")
                    print(f"    Mean: {subvalue['mean']*1000:.3f} ms")
                    print(f"    Std:  {subvalue['std']*1000:.3f} ms")
                else:
                    print(f"  {subkey}: {subvalue}")
        else:
            print(f"{key}: {value}")
    
    print(f"{'='*60}")