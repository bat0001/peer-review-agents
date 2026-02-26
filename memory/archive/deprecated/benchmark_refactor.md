# Benchmark Refactor Plan - Move Everything to __main__.py

**STATUS: DEPRECATED - Partially implemented, then abandoned**
- ✅ Completed: Removed `benchmark()` functions from all benchmark files
- ❌ Not implemented: `measure_implementations()` in `core.py`, removal of `run_single_case()`
- Current design keeps `run_single_case()` in base class, which works fine

## Problem
Current design has unnecessary layers:
- Each benchmark file has a `benchmark()` function that orchestrates measurement
- `__main__.py` just calls these `benchmark()` functions and formats output
- Measurement logic scattered between base class `run_single_case()` and `benchmark()` functions
- Too much indirection

## Solution
**Put ALL orchestration logic in `__main__.py`**

### Principle
- **Classes**: Data setup + implementation creation only (pure)
- **Benchmark files**: Just export the class, nothing else
- **`__main__.py`**: ALL orchestration - create instances, measure, format output

## Current Structure (Too Complex)

```
benchmark/permutation/gather/benchmark.py:
  - class GatherBenchmark(BaseBenchmark)
  - def benchmark(...) -> OrderedDict  # Orchestrates cases

benchmark/permutation/__main__.py:
  - Parses args
  - Calls benchmark() function
  - Formats output
```

## New Structure (Simple)

```
benchmark/permutation/gather/benchmark.py:
  - class GatherBenchmark(BaseBenchmark)
  # NO benchmark() function!

benchmark/permutation/__main__.py:
  - Parses args
  - Creates GatherBenchmark instances directly
  - Measures all implementations
  - Formats and prints output
```

## Implementation Plan

### Step 1: Add measurement utilities to core.py

```python
# In core.py
def measure_implementations(
    implementations: Dict[str, Tuple[Callable, Callable, Dict]],
    config: BenchmarkConfig,
    bytes_moved: float,
    reference_name: str = 'torch',
    weight_grads: Optional[Dict[str, torch.Tensor]] = None,
) -> List[BenchmarkResult]:
    """
    Measure all implementations and compare against reference.

    Args:
        implementations: Dict of (runner_fn, output_fn, extras)
        config: Benchmark configuration
        bytes_moved: Total bytes moved for bandwidth calculation
        reference_name: Name of reference implementation
        weight_grads: Optional dict of weight gradients for checking

    Returns:
        List of BenchmarkResults
    """
    reference = implementations[reference_name][1]().detach().to(torch.float32)
    weights_reference = weight_grads.get(reference_name) if weight_grads else None
    tolerance = get_tolerance(config.dtype)

    results = []
    for name, (runner, output_fn, extras) in implementations.items():
        torch.cuda.reset_peak_memory_stats(config.device)
        time_ms = measure(runner, repeats=config.repeats, warmup=config.warmup)
        peak_bytes = torch.cuda.max_memory_allocated(config.device)
        out = output_fn().detach().to(torch.float32)
        extras_copy = dict(extras)

        # Validate output
        if name == reference_name:
            matches = True
            diff = None
        else:
            diff_tensor = (out - reference).abs()
            diff = float(diff_tensor.max()) if diff_tensor.numel() > 0 else 0.0
            matches = diff <= tolerance

        # Check weight gradients if provided
        if weight_grads and weights_reference is not None and name != reference_name:
            candidate = weight_grads.get(name)
            if candidate is None:
                matches = False
                extras_copy['grad_w_match'] = False
            else:
                grad_w_diff = (candidate.to(torch.float32) - weights_reference.to(torch.float32)).abs()
                max_grad_w_diff = float(grad_w_diff.max()) if grad_w_diff.numel() > 0 else 0.0
                extras_copy['grad_w_max'] = max_grad_w_diff
                grad_match = max_grad_w_diff <= tolerance
                extras_copy['grad_w_match'] = grad_match
                matches = matches and grad_match

        results.append(
            BenchmarkResult(
                name=name,
                time_ms=time_ms,
                gbps=bytes_moved / time_ms / 1e6,
                bytes_moved=bytes_moved,
                matches=matches,
                max_abs_diff=diff,
                peak_mem_gb=peak_bytes / 1e9,
                extras=extras_copy,
            )
        )

    return results
```

### Step 2: Simplify base class - remove run methods

```python
# In base.py
class BaseBenchmark(ABC):
    """Base class for benchmarks - NO measurement logic."""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.device = config.device
        self.compile_manager = TorchCompileManager()

    @abstractmethod
    def setup_data(self) -> None:
        """Setup benchmark data tensors."""
        ...

    @abstractmethod
    def create_implementations(self) -> Dict[str, Tuple[Callable, Callable, Dict]]:
        """Create benchmark implementations."""
        ...

    @abstractmethod
    def compute_bytes(self) -> float:
        """Compute total bytes moved."""
        ...

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get additional statistics."""
        return {}

    # REMOVED: run_single_case()
    # REMOVED: run_autograd_case()
```

### Step 3: Remove benchmark() functions from all files

**gather/benchmark.py**: Just the class
```python
class GatherBenchmark(BaseKernelBenchmark):
    def __init__(self, config: BenchmarkConfig, use_weights: bool = True):
        ...

    def setup_data(self):
        ...

    def create_implementations(self):
        ...

    def compute_bytes(self):
        ...

# NO benchmark() function!
```

**scatter/benchmark.py**: Just the classes
```python
class DenseScatterBenchmark(BaseKernelBenchmark):
    ...

class AtomicScatterBenchmark(BaseKernelBenchmark):
    ...

# NO benchmark() function!
```

**gatherop/benchmark.py**: Just the class
```python
class GatherOpBenchmark(BaseAutogradBenchmark):
    ...

# NO benchmark() function!
```

**scatterop/benchmark.py**: Just the class
```python
class ScatterOpBenchmark(BaseBenchmark):
    def __init__(self, config, mode='forward', weights_requires_grad=True):
        ...

# NO benchmark() function!
```

### Step 4: Move ALL logic to __main__.py

```python
# In __main__.py
def run_gather_benchmark(config, args):
    """Run gather benchmark."""
    print(
        f'[gather] tokens={config.num_tokens:,} hidden={config.hidden} '
        f'experts={config.num_experts} density={config.density:.4f} '
        f'dtype={args.dtype} repeats={config.repeats} warmup={config.warmup}'
    )

    from benchmark.permutation.gather.benchmark import GatherBenchmark

    case_titles = {
        'weights': 'GATHER KERNELS (weights fused)',
        'weights_none': 'GATHER KERNELS (weights=None)',
    }

    # Run with weights
    bm = GatherBenchmark(config, use_weights=True)
    bm.setup_data()
    implementations = bm.create_implementations()
    results = measure_implementations(
        implementations,
        config,
        bytes_moved=bm.compute_bytes(),
    )
    print_results('weights', results, bm.get_stats(), case_titles, bm.compile_manager)

    # Run without weights
    bm = GatherBenchmark(config, use_weights=False)
    bm.setup_data()
    implementations = bm.create_implementations()
    results = measure_implementations(
        implementations,
        config,
        bytes_moved=bm.compute_bytes(),
    )
    print_results('weights_none', results, bm.get_stats(), case_titles, bm.compile_manager)


def run_scatter_benchmark(config, args):
    """Run scatter benchmark."""
    print(f'[scatter] ...')

    from benchmark.permutation.scatter.benchmark import (
        AtomicScatterBenchmark,
        DenseScatterBenchmark,
    )

    case_titles = {
        'scatter': 'SCATTER (BUFFER + REDUCE)',
        'scatter_atomic': 'SCATTER WITH ATOMIC ADD',
    }

    # Dense scatter
    bm = DenseScatterBenchmark(config)
    bm.setup_data()
    implementations = bm.create_implementations()
    results = measure_implementations(implementations, config, bytes_moved=bm.compute_bytes())
    print_results('scatter', results, bm.get_stats(), case_titles, bm.compile_manager)

    # Atomic scatter
    bm = AtomicScatterBenchmark(config)
    bm.setup_data()
    implementations = bm.create_implementations()
    results = measure_implementations(implementations, config, bytes_moved=bm.compute_bytes())
    print_results('scatter_atomic', results, bm.get_stats(), case_titles, bm.compile_manager)


def run_scatterop_benchmark(config, args):
    """Run scatterop benchmark."""
    print(f'[scatterop] ...')

    from benchmark.permutation.scatterop.benchmark import ScatterOpBenchmark

    case_titles = {
        'forward': 'SCATTER OP FORWARD',
        'backward-with-wgrad': 'SCATTER OP BACKWARD (with weight grad)',
        'backward-no-wgrad': 'SCATTER OP BACKWARD (no weight grad)',
        'backward-kernel-wgrad': 'BACKWARD KERNEL ONLY (WITH weight grad)',
        'backward-kernel-no-wgrad': 'BACKWARD KERNEL ONLY (NO weight grad)',
    }

    # Forward
    bm = ScatterOpBenchmark(config, mode='forward')
    bm.setup_data()
    implementations = bm.create_implementations()
    results = measure_implementations(implementations, config, bytes_moved=bm.compute_bytes())
    print_results('forward', results, bm.get_stats(), case_titles, bm.compile_manager)

    # Backward with weight grad
    bm = ScatterOpBenchmark(config, mode='backward', weights_requires_grad=True)
    bm.setup_data()
    implementations = bm.create_implementations()
    results = measure_implementations(
        implementations, config, bytes_moved=bm.compute_bytes(), weight_grads=bm.weight_grads
    )
    print_results('backward-with-wgrad', results, bm.get_stats(), case_titles, bm.compile_manager)

    # ... more cases


def print_results(key, results, stats, case_titles, compile_manager):
    """Print formatted results."""
    title = case_titles.get(key, f'[{key}]')
    print('=' * 88)
    print(f' {title} '.center(88, '='))
    print('=' * 88)
    print(format_results(results))
    print('=' * 88)

    # Add compile stats
    if compile_manager:
        compile_stats = compile_manager.get_stats()
        if compile_stats.get('available'):
            stats['compile'] = compile_stats

    stats_block = format_stats(stats)
    if stats_block:
        print()
        print('INFO:', stats_block)
    print()


def main():
    setup_environment()
    parser = argparse.ArgumentParser(...)
    parser.add_argument('--mode', ...)
    args, remaining = parser.parse_known_args()

    if args.mode == 'suite':
        from benchmark.permutation.suite import main as suite_main
        suite_main()
    else:
        # Parse standard args
        parser2 = argparse.ArgumentParser()
        add_standard_args(parser2)
        args2 = parser2.parse_args(remaining)
        config = args_to_config(args2)

        # Dispatch to appropriate benchmark runner
        if args.mode == 'gather':
            run_gather_benchmark(config, args2)
        elif args.mode == 'scatter':
            run_scatter_benchmark(config, args2)
        elif args.mode == 'gatherop':
            run_gatherop_benchmark(config, args2)
        elif args.mode == 'scatterop':
            run_scatterop_benchmark(config, args2)
```

### Step 5: Update __init__.py exports

```python
# In benchmark/permutation/__init__.py
"""Permutation benchmark classes."""

from .gather.benchmark import GatherBenchmark
from .gatherop.benchmark import GatherOpBenchmark
from .scatter.benchmark import AtomicScatterBenchmark, DenseScatterBenchmark
from .scatterop.benchmark import ScatterOpBenchmark

__all__ = [
    'GatherBenchmark',
    'GatherOpBenchmark',
    'DenseScatterBenchmark',
    'AtomicScatterBenchmark',
    'ScatterOpBenchmark',
]

# NO benchmark functions exported!
```

### Step 6: Update subdirectory __init__.py

```python
# In benchmark/permutation/gather/__init__.py
from .benchmark import GatherBenchmark

__all__ = ['GatherBenchmark']

# NO benchmark function!
```

## Files to Change

1. **`core.py`**: Add `measure_implementations()` function (~60 lines)
2. **`base.py`**: Remove `run_single_case()` and `run_autograd_case()` (~-100 lines)
3. **`__main__.py`**: Add `run_*_benchmark()` functions (~+200 lines, but clearer)
4. **`gather/benchmark.py`**: Remove `benchmark()` function (~-50 lines)
5. **`scatter/benchmark.py`**: Remove `benchmark()` function (~-50 lines)
6. **`gatherop/benchmark.py`**: Remove `benchmark()` function (~-50 lines)
7. **`scatterop/benchmark.py`**: Remove `benchmark()` function and custom `run_single_case()` (~-100 lines)
8. **`benchmark/permutation/__init__.py`**: Remove benchmark function exports (~-5 lines)
9. **`{gather,scatter,gatherop,scatterop}/__init__.py`**: Remove benchmark exports (~-4 lines each)

## Benefits

1. **Single source of truth**: ALL orchestration in `__main__.py`
2. **Classes are pure**: Just data + implementations, no side effects
3. **Easy to understand**: Read `__main__.py` to see the full flow
4. **Less indirection**: No need to jump between files
5. **Easier to customize**: Want different output? Just modify `__main__.py`
6. **No duplicate benchmark() functions**: One pattern in `__main__.py`

## Expected Line Changes

- Remove ~350 lines (benchmark functions + run methods)
- Add ~200 lines (orchestration in __main__.py)
- **Net: -150 lines**

## Final File Sizes (Estimated)

- `__main__.py`: 119 → 320 lines (all logic in one place)
- `base.py`: 263 → 160 lines (remove run methods)
- `gather/benchmark.py`: 149 → 100 lines
- `scatter/benchmark.py`: 250 → 200 lines
- `gatherop/benchmark.py`: 152 → 100 lines
- `scatterop/benchmark.py`: 504 → 400 lines

**Total: 1,956 → ~1,800 lines**

## Key Insight

**Benchmark files become simple class definitions. All the "how to run" logic lives in one place: `__main__.py`.**

This is much cleaner and follows the principle: "Tell, don't ask."