"""Quick test for sequential scatter integration."""

import torch
from benchmark.permutation.scatter.benchmark import build_inverse_indices
from src.kernels.sequential import _sequential_add

# Setup test data
num_tokens = 512
num_experts = 8  # G=2, E=4
capacity = 64  # 512 tokens / 8 experts
hidden = 256
max_experts = 8  # G * E

device = torch.device('cuda')

# Create test tensors
expert_out = torch.randn((num_experts, capacity, hidden), dtype=torch.bfloat16, device=device)
expert_out_flat = expert_out.view(-1, hidden)

# Create routing indices (random for testing)
# Note: Using proper topk-style indices where each expert picks capacity tokens
scores = torch.randn((num_experts, num_tokens), dtype=torch.float32, device=device)
indices_2d = torch.topk(scores, k=capacity, dim=1, largest=True).indices
indices = indices_2d.reshape(-1)  # Flatten to (num_experts * capacity,)
weights = torch.rand(num_experts * capacity, dtype=torch.float32, device=device)

print(f"Test configuration:")
print(f"  num_tokens={num_tokens}, hidden={hidden}")
print(f"  num_experts={num_experts}, capacity={capacity}")
print(f"  max_experts={max_experts}")
print(f"  expert_out shape: {expert_out.shape}")
print(f"  indices shape: {indices.shape}")
print(f"  weights shape: {weights.shape}")

# Build inverse indices
print("\nBuilding inverse indices...")
print(f"  Using benchmark.build_inverse_indices (expects flat indices)")
try:
    inverse_indices = build_inverse_indices(indices, num_tokens, max_experts)
    print(f"  inverse_indices shape: {inverse_indices.shape}")

    # Debug: check some values
    print(f"  Sample inverse_indices[0]: {inverse_indices[0].tolist()[:5]}")

    # Count how many valid entries per token
    valid_counts = (inverse_indices != -1).sum(dim=1)
    print(f"  Valid entries per token - min: {valid_counts.min()}, max: {valid_counts.max()}, mean: {valid_counts.float().mean():.2f}")

    print(f"  Success!")
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test sequential kernel
print("\nTesting sequential scatter kernel...")
try:
    out = torch.zeros((num_tokens, hidden), dtype=torch.bfloat16, device=device)
    _sequential_add[num_tokens,](
        expert_out_flat,
        out,
        inverse_indices,
        weights,
        MAX_EXPERTS=max_experts,
        NUM_COLUMNS=hidden,
        SCALE=True,
        ADD_INTO=False,
    )
    print(f"  Output shape: {out.shape}")
    print(f"  Output mean: {out.mean().item():.6f}")
    print(f"  Output std: {out.std().item():.6f}")
    print(f"  Success!")
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Compare with torch atomic scatter
print("\nComparing with torch atomic scatter...")
try:
    weighted = torch.mul(expert_out_flat, weights.view(-1, 1))
    out_torch = torch.zeros((num_tokens, hidden), dtype=torch.bfloat16, device=device)
    out_torch.index_add_(0, indices, weighted.to(out_torch.dtype))

    diff = (out - out_torch).abs()
    max_diff = diff.max().item()
    mean_diff = diff.mean().item()

    print(f"  Max difference: {max_diff:.6e}")
    print(f"  Mean difference: {mean_diff:.6e}")

    # Check which tokens have the largest differences
    token_max_diff = diff.max(dim=1).values
    worst_token = token_max_diff.argmax().item()
    print(f"  Worst token: {worst_token}, diff: {token_max_diff[worst_token]:.6e}")

    # Check that token's inverse_indices
    print(f"  Token {worst_token} inverse_indices: {inverse_indices[worst_token].tolist()}")

    # Check outputs for that token
    print(f"  Sequential output[{worst_token}]: mean={out[worst_token].float().mean():.6f}, std={out[worst_token].float().std():.6f}")
    print(f"  Torch output[{worst_token}]: mean={out_torch[worst_token].float().mean():.6f}, std={out_torch[worst_token].float().std():.6f}")

    # BF16 tolerance should be around 1e-2 for moderate values
    if max_diff < 0.05:  # Relax threshold for bf16
        print(f"  ✓ Results match within BF16 tolerance!")
    else:
        print(f"  ✗ Results differ significantly!")
        exit(1)
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n✓ All tests passed!")
