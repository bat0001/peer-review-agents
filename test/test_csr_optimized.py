"""Test Optimized CSR scatter backward kernel correctness."""

import torch
# import pytest
from src.ops.csr_optimized import csr_scatter_sum_optimized
from src.kernels.csr import build_slot_indices

def test_csr_optimized_correctness():
    """Verify Optimized CSR scatter produces same results and gradients as reference."""
    torch.manual_seed(42)
    device = "cuda"
    if not torch.cuda.is_available():
        print("CUDA not available, skipping")
        return

    # Setup
    E, C, N, H = 3, 5, 8, 32
    max_experts = 4
    
    # Inputs
    expert_slots = torch.randn(E * C, H, device=device, dtype=torch.bfloat16, requires_grad=True)
    weights = torch.rand(E * C, device=device, dtype=torch.bfloat16, requires_grad=True)
    add_into = torch.randn(N, H, device=device, dtype=torch.bfloat16, requires_grad=True)
    
    # Routing
    router_logits = torch.randn(E, N, device=device)
    _, indices = torch.topk(router_logits, k=C, dim=1)
    indices = indices.to(torch.int32)
    
    # Build CSR indices
    slot_idx, slot_offs, counts = build_slot_indices(indices, num_tokens=N, max_experts=max_experts)

    # === 1. Optimized CSR ===
    # Forward
    out_csr = csr_scatter_sum_optimized(
        expert_slots, indices, N, max_experts, 
        slot_idx, slot_offs, counts, 
        weights=weights, 
        add_into_tensor=add_into
    )
    
    # Backward
    grad_out = torch.randn_like(out_csr)
    out_csr.backward(grad_out)
    
    grad_slots_csr = expert_slots.grad.clone()
    grad_weights_csr = weights.grad.clone()
    grad_add_into_csr = add_into.grad.clone()
    
    expert_slots.grad = None
    weights.grad = None
    add_into.grad = None

    # === 2. Reference (Index Add) ===
    # Forward
    ref_out = add_into.clone()
    flat_indices = indices.reshape(-1)
    weighted_slots = expert_slots * weights.unsqueeze(1)
    ref_out.index_add_(0, flat_indices, weighted_slots)
    
    # Backward
    ref_out.backward(grad_out)
    
    grad_slots_ref = expert_slots.grad
    grad_weights_ref = weights.grad
    grad_add_into_ref = add_into.grad

    # === Compare ===
    print(f"\nMax diff output: {(out_csr - ref_out).abs().max().item()}")
    print(f"Max diff grad_slots: {(grad_slots_csr - grad_slots_ref).abs().max().item()}")
    print(f"Max diff grad_weights: {(grad_weights_csr - grad_weights_ref).abs().max().item()}")
    print(f"Max diff grad_add_into: {(grad_add_into_csr - grad_add_into_ref).abs().max().item()}")

    assert torch.allclose(out_csr, ref_out, atol=1e-2, rtol=1e-2)
    assert torch.allclose(grad_slots_csr, grad_slots_ref, atol=1e-2, rtol=1e-2)
    assert torch.allclose(grad_weights_csr, grad_weights_ref, atol=1e-2, rtol=1e-2)
    assert torch.allclose(grad_add_into_csr, grad_add_into_ref, atol=1e-2, rtol=1e-2)
    
    # Check grad_add_into is exactly grad_out (identity backward)
    assert torch.allclose(grad_add_into_csr, grad_out, atol=1e-5)
    print("✓ Correctness test passed")

if __name__ == "__main__":
    test_csr_optimized_correctness()

