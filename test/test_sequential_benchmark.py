"""Test sequential scatter in benchmark framework."""

from benchmark.permutation.core import BenchmarkConfig
from benchmark.permutation.scatter.benchmark import AtomicScatterBenchmark

# Create config
config = BenchmarkConfig(
    num_tokens=512,
    hidden=256,
    granularity=2,  # G
    expansion=4,    # E
    repeats=3,
    warmup=1,
    num_experts=8,  # G * E = 2 * 4
)

print(f"Creating AtomicScatterBenchmark...")
print(f"  Config: tokens={config.num_tokens}, hidden={config.hidden}")
print(f"  G={config.granularity}, E={config.expansion}, experts={config.num_experts}")

# Create benchmark
benchmark = AtomicScatterBenchmark(config)

print(f"\nSetting up data...")
benchmark.setup_data()

print(f"  ✓ Data setup complete")
print(f"  indices shape: {benchmark.indices.shape}")
print(f"  inverse_indices shape: {benchmark.inverse_indices.shape}")
print(f"  max_experts: {benchmark.max_experts}")

print(f"\nCreating implementations...")
implementations = benchmark.create_implementations()

print(f"  Available implementations: {list(implementations.keys())}")

if 'sequential' not in implementations:
    print(f"  ✗ sequential implementation not found!")
    exit(1)

print(f"  ✓ sequential implementation found")

# Test running the sequential implementation
print(f"\nTesting sequential implementation...")
runner, output_fn, extras = implementations['sequential']

try:
    # Run once
    result = output_fn()
    print(f"  Output shape: {result.shape}")
    print(f"  Output mean: {result.float().mean().item():.6f}")
    print(f"  Output std: {result.float().std().item():.6f}")
    print(f"  ✓ Sequential implementation runs successfully")
except Exception as e:
    print(f"  ✗ Error running sequential: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Compare with torch implementation
print(f"\nComparing with torch implementation...")
torch_runner, torch_output_fn, torch_extras = implementations['torch']

try:
    torch_result = torch_output_fn()
    diff = (result - torch_result).abs()
    max_diff = diff.max().item()
    mean_diff = diff.mean().item()

    print(f"  Max difference: {max_diff:.6e}")
    print(f"  Mean difference: {mean_diff:.6e}")

    if max_diff < 0.05:
        print(f"  ✓ Results match within BF16 tolerance!")
    else:
        print(f"  ✗ Results differ significantly!")
        exit(1)
except Exception as e:
    print(f"  ✗ Error comparing: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print(f"\n✓ All benchmark integration tests passed!")
