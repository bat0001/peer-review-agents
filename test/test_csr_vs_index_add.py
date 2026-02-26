"""Test CSR scatter kernel correctness and performance vs index_add."""

import torch
import time

from src.ops.csr import csr_scatter_sum
from src.kernels.csr import build_slot_indices


def test_csr_correctness():
    """Verify CSR scatter produces same results as index_add."""
    torch.manual_seed(42)
    device = "cuda"

    # Setup: E=3 experts, C=5 capacity, N=8 tokens, H=16 hidden
    E, C, N, H = 3, 5, 8, 16
    max_experts = 4

    # Simulate GEC routing: each expert selects top-k tokens
    # Create fake router logits and use topk
    router_logits = torch.randn(E, N, device=device)  # (E, N)

    # Each expert selects top-C tokens
    _, indices = torch.topk(router_logits, k=C, dim=1)  # (E, C)
    indices = indices.to(torch.int32)

    # Expert outputs
    expert_slots = torch.randn(E * C, H, device=device, dtype=torch.bfloat16)

    # Weights
    weights = torch.rand(E * C, device=device, dtype=torch.bfloat16)

    # === Method 1: CSR scatter ===
    slot_idx, slot_offs, counts = build_slot_indices(indices, num_tokens=N, max_experts=max_experts)
    csr_out = csr_scatter_sum(
        expert_slots,
        indices,
        N,
        max_experts,
        weights_flat=weights,
        add_into=False,
        slot_indices=slot_idx,
        slot_offsets=slot_offs,
        slot_counts=counts,
    )

    # === Method 2: index_add (reference) ===
    ref_out = torch.zeros(N, H, device=device, dtype=torch.bfloat16)
    flat_indices = indices.reshape(-1)  # (E*C,)

    # Apply weights and scatter with index_add
    weighted_slots = expert_slots * weights.unsqueeze(1)
    ref_out.index_add_(0, flat_indices, weighted_slots)

    # Compare
    print("CSR output shape:", csr_out.shape)
    print("Ref output shape:", ref_out.shape)
    print("Max diff:", (csr_out - ref_out).abs().max().item())
    print("Mean diff:", (csr_out - ref_out).abs().mean().item())

    # Check correctness
    assert torch.allclose(csr_out, ref_out, atol=1e-2, rtol=1e-2), "CSR output doesn't match reference!"
    print("✓ CSR correctness test passed!")

    # Print count distribution
    print(f"\nCount distribution: {counts.tolist()}")
    print(f"Mean experts/token: {counts.float().mean().item():.2f}")


def benchmark_csr_vs_index_add():
    """Benchmark CSR vs index_add performance."""
    torch.manual_seed(42)
    device = "cuda"

    # Realistic scale: B=4 seqs, T=512 tokens/seq, E=8 experts, k=256 tokens/expert
    B, T, E = 4, 512, 8
    N = B * T  # 2048 tokens
    k = 256  # capacity per expert
    C = k
    H = 512  # hidden dim
    max_experts = 4

    # Generate GEC-style routing: each expert selects top-k tokens
    router_logits = torch.randn(E, N, device=device)
    _, indices = torch.topk(router_logits, k=C, dim=1)  # (E, C)
    indices = indices.to(torch.int32)
    expert_slots = torch.randn(E * C, H, device=device, dtype=torch.bfloat16)
    weights = torch.rand(E * C, device=device, dtype=torch.bfloat16)

    # Build CSR structures
    slot_idx, slot_offs, counts = build_slot_indices(indices, num_tokens=N, max_experts=max_experts)

    print(f"\nBenchmark setup: N={N}, E={E}, C={C}, H={H}")
    print(f"Count distribution - min: {counts.min().item()}, max: {counts.max().item()}, mean: {counts.float().mean().item():.2f}")

    # Warmup
    for _ in range(10):
        _ = csr_scatter_sum(
            expert_slots,
            indices,
            N,
            max_experts,
            weights_flat=weights,
            slot_indices=slot_idx,
            slot_offsets=slot_offs,
            slot_counts=counts,
        )
    torch.cuda.synchronize()

    # Benchmark CSR
    repeats = 100
    start = time.perf_counter()
    for _ in range(repeats):
        csr_out = csr_scatter_sum(
            expert_slots,
            indices,
            N,
            max_experts,
            weights_flat=weights,
            slot_indices=slot_idx,
            slot_offsets=slot_offs,
            slot_counts=counts,
        )
    torch.cuda.synchronize()
    csr_time = (time.perf_counter() - start) / repeats * 1000

    # Benchmark index_add
    flat_indices = indices.reshape(-1)

    # Warmup
    for _ in range(10):
        ref_out = torch.zeros(N, H, device=device, dtype=torch.bfloat16)
        weighted = expert_slots * weights.unsqueeze(1)
        ref_out.index_add_(0, flat_indices, weighted)
    torch.cuda.synchronize()

    start = time.perf_counter()
    for _ in range(repeats):
        ref_out = torch.zeros(N, H, device=device, dtype=torch.bfloat16)
        weighted = expert_slots * weights.unsqueeze(1)
        ref_out.index_add_(0, flat_indices, weighted)
    torch.cuda.synchronize()
    index_add_time = (time.perf_counter() - start) / repeats * 1000

    print(f"\nResults ({repeats} iterations):")
    print(f"CSR scatter:  {csr_time:.3f} ms")
    print(f"index_add:    {index_add_time:.3f} ms")
    print(f"Speedup:      {index_add_time / csr_time:.2f}x")

    if csr_time < index_add_time:
        print("✓ CSR is faster!")
    else:
        print("✗ CSR is slower - needs further optimization")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing CSR Scatter Kernel")
    print("=" * 60)

    test_csr_correctness()
    print("\n" + "=" * 60)
    benchmark_csr_vs_index_add()
    print("=" * 60)
