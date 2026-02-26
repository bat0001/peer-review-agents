"""Validation benchmark to compare GECMLP against reference implementation."""

import torch
import torch.nn as nn
import argparse
import sys
import os
from typing import Dict, Any, List, Tuple, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.gec import GECMLP, GECMLPReference
from src.models.model_base import ModelConfig


def transfer_weights(source: nn.Module, target: nn.Module) -> None:
    """Transfer weights from source model to target model."""
    source_state = source.state_dict()
    target_state = target.state_dict()
    
    # Check that both models have the same parameters
    if set(source_state.keys()) != set(target_state.keys()):
        missing_in_target = set(source_state.keys()) - set(target_state.keys())
        missing_in_source = set(target_state.keys()) - set(source_state.keys())
        
        error_msg = "Parameter mismatch between models:\n"
        if missing_in_target:
            error_msg += f"Missing in target: {missing_in_target}\n"
        if missing_in_source:
            error_msg += f"Missing in source: {missing_in_source}\n"
        raise ValueError(error_msg)
    
    # Copy weights with shape validation
    for name, param in source_state.items():
        if param.shape != target_state[name].shape:
            raise ValueError(f"Shape mismatch for {name}: {param.shape} vs {target_state[name].shape}")
        target_state[name].copy_(param)
    
    print("✓ Weight transfer completed successfully")


def compare_tensors(
    tensor1: torch.Tensor, 
    tensor2: torch.Tensor, 
    name: str,
    rtol: float = 1e-5,
    atol: float = 1e-6
) -> bool:
    """Compare two tensors with detailed error reporting."""
    if tensor1.shape != tensor2.shape:
        print(f"✗ {name}: Shape mismatch {tensor1.shape} vs {tensor2.shape}")
        return False
    
    if torch.allclose(tensor1, tensor2, rtol=rtol, atol=atol):
        print(f"✓ {name}: Match (max diff: {torch.max(torch.abs(tensor1 - tensor2)).item():.2e})")
        return True
    else:
        diff = torch.abs(tensor1 - tensor2)
        max_diff = torch.max(diff).item()
        mean_diff = torch.mean(diff).item()
        rel_diff = max_diff / (torch.max(torch.abs(tensor1)).item() + 1e-8)
        
        print(f"✗ {name}: Mismatch")
        print(f"  Max absolute diff: {max_diff:.2e}")
        print(f"  Mean absolute diff: {mean_diff:.2e}")
        print(f"  Max relative diff: {rel_diff:.2e}")
        print(f"  Tolerance: rtol={rtol:.2e}, atol={atol:.2e}")
        
        # Show a few specific mismatches
        mismatch_mask = diff > atol + rtol * torch.abs(tensor1)
        if mismatch_mask.any():
            mismatch_indices = torch.nonzero(mismatch_mask, as_tuple=False)[:5]  # Show first 5
            print(f"  Sample mismatches:")
            for idx in mismatch_indices:
                idx_tuple = tuple(idx.tolist())
                val1 = tensor1[idx_tuple].item()
                val2 = tensor2[idx_tuple].item()
                print(f"    {idx_tuple}: {val1:.6e} vs {val2:.6e} (diff: {abs(val1-val2):.2e})")
        
        return False


def validate_forward_pass(
    model_current: GECMLP,
    model_reference: GECMLPReference,
    input_tensor: torch.Tensor,
    rtol: float = 1e-5,
    atol: float = 1e-6
) -> bool:
    """Validate forward pass outputs match between models."""
    print("\n" + "="*60)
    print("FORWARD PASS VALIDATION")
    print("="*60)
    
    model_current.eval()
    model_reference.eval()
    
    with torch.no_grad():
        # Forward pass through both models
        output_current, metrics_current = model_current(input_tensor)
        output_reference, metrics_reference = model_reference(input_tensor)
        
        # Compare main outputs
        output_match = compare_tensors(
            output_current, output_reference, "Forward output", rtol, atol
        )
        
        # Compare metrics
        metrics_match = True
        metric_keys = set(metrics_current.keys()) | set(metrics_reference.keys())
        
        for key in sorted(metric_keys):
            if key not in metrics_current:
                print(f"✗ Metric {key}: Missing in current model")
                metrics_match = False
                continue
            if key not in metrics_reference:
                print(f"✗ Metric {key}: Missing in reference model")
                metrics_match = False
                continue
                
            metric_match = compare_tensors(
                metrics_current[key], metrics_reference[key], f"Metric {key}", rtol, atol
            )
            metrics_match = metrics_match and metric_match
        
        overall_match = output_match and metrics_match
        print(f"\nForward pass validation: {'✓ PASS' if overall_match else '✗ FAIL'}")
        return overall_match


def validate_backward_pass(
    model_current: GECMLP,
    model_reference: GECMLPReference,
    input_tensor: torch.Tensor,
    rtol: float = 1e-4,
    atol: float = 1e-5
) -> bool:
    """Validate backward pass gradients match between models."""
    print("\n" + "="*60)
    print("BACKWARD PASS VALIDATION")
    print("="*60)
    
    model_current.train()
    model_reference.train()
    
    # Clear any existing gradients
    model_current.zero_grad()
    model_reference.zero_grad()
    
    # Forward pass with gradient tracking
    input_current = input_tensor.clone().requires_grad_(True)
    input_reference = input_tensor.clone().requires_grad_(True)
    
    output_current, _ = model_current(input_current)
    output_reference, _ = model_reference(input_reference)
    
    # Create identical loss (sum of outputs for simplicity)
    loss_current = output_current.sum()
    loss_reference = output_reference.sum()
    
    # Backward pass
    loss_current.backward()
    loss_reference.backward()
    
    # Compare gradients for all parameters
    current_params = dict(model_current.named_parameters())
    reference_params = dict(model_reference.named_parameters())
    
    gradient_match = True
    for name in sorted(current_params.keys()):
        if name not in reference_params:
            print(f"✗ Parameter {name}: Missing in reference model")
            gradient_match = False
            continue
            
        current_grad = current_params[name].grad
        reference_grad = reference_params[name].grad
        
        if current_grad is None and reference_grad is None:
            print(f"✓ {name}.grad: Both None")
            continue
        elif current_grad is None or reference_grad is None:
            print(f"✗ {name}.grad: One is None, other is not")
            gradient_match = False
            continue
        
        param_match = compare_tensors(
            current_grad, reference_grad, f"{name}.grad", rtol, atol
        )
        gradient_match = gradient_match and param_match
    
    # Also compare input gradients
    if input_current.grad is not None and input_reference.grad is not None:
        input_grad_match = compare_tensors(
            input_current.grad, input_reference.grad, "input.grad", rtol, atol
        )
        gradient_match = gradient_match and input_grad_match
    
    print(f"\nBackward pass validation: {'✓ PASS' if gradient_match else '✗ FAIL'}")
    return gradient_match


def run_validation_test(
    batch_size: int,
    seq_len: int,
    n_embd: int,
    n_experts: int,
    expert_dim: int,
    density: float,
    rtol: float = 1e-5,
    atol: float = 1e-6,
    backward_rtol: float = 1e-4,
    backward_atol: float = 1e-5
) -> bool:
    """Run a complete validation test with given configuration."""
    print(f"\n{'='*80}")
    print(f"VALIDATION TEST")
    print(f"{'='*80}")
    print(f"Config: B={batch_size}, T={seq_len}, C={n_embd}")
    print(f"GEC: {n_experts} experts, expert_dim={expert_dim}, density={density}")
    print(f"Tolerances: forward(rtol={rtol:.2e}, atol={atol:.2e}), backward(rtol={backward_rtol:.2e}, atol={backward_atol:.2e})")
    
    # Create configuration
    config = ModelConfig(
        n_embd=n_embd,
        n_experts=n_experts,
        expert_dim=expert_dim,
        density=density
    )
    
    # Create models
    print("\nInitializing models...")
    model_current = GECMLP(config).cuda()
    model_reference = GECMLPReference(config).cuda()
    
    # Transfer weights from reference to current to ensure identical initialization
    print("Transferring weights from reference to current...")
    transfer_weights(model_reference, model_current)
    
    # Create random input
    print(f"Creating random input tensor...")
    input_tensor = torch.randn(batch_size, seq_len, n_embd).cuda()
    
    # Run forward validation
    forward_pass = validate_forward_pass(
        model_current, model_reference, input_tensor, rtol, atol
    )
    
    # Run backward validation
    backward_pass = validate_backward_pass(
        model_current, model_reference, input_tensor, backward_rtol, backward_atol
    )
    
    overall_pass = forward_pass and backward_pass
    print(f"\n{'='*80}")
    print(f"OVERALL RESULT: {'✓ PASS' if overall_pass else '✗ FAIL'}")
    print(f"{'='*80}")
    
    return overall_pass


def main():
    """Main validation script."""
    parser = argparse.ArgumentParser(description="Validate GECMLP against reference implementation")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size")
    parser.add_argument("--seq-len", type=int, default=8, help="Sequence length")
    parser.add_argument("--n-embd", type=int, default=128, help="Embedding dimension")
    parser.add_argument("--n-experts", type=int, default=4, help="Number of experts")
    parser.add_argument("--expert-dim", type=int, default=256, help="Expert hidden dimension")
    parser.add_argument("--density", type=float, default=0.25, help="Expert density")
    parser.add_argument("--rtol", type=float, default=1e-5, help="Relative tolerance for forward pass")
    parser.add_argument("--atol", type=float, default=1e-6, help="Absolute tolerance for forward pass")
    parser.add_argument("--backward-rtol", type=float, default=1e-4, help="Relative tolerance for backward pass")
    parser.add_argument("--backward-atol", type=float, default=1e-5, help="Absolute tolerance for backward pass")
    parser.add_argument("--all-configs", action="store_true", help="Run multiple test configurations")
    
    args = parser.parse_args()
    
    if args.all_configs:
        # Run multiple test configurations
        test_configs = [
            # (batch_size, seq_len, n_embd, n_experts, expert_dim, density)
            (2, 4, 64, 2, 128, 0.5),           # Tiny
            (4, 8, 128, 4, 256, 0.25),         # Small  
            (8, 16, 256, 8, 512, 0.125),       # Medium
            (16, 32, 512, 16, 1024, 0.0625),   # Large
        ]
        
        print(f"Running {len(test_configs)} test configurations...")
        
        all_passed = True
        for i, (bs, sl, emb, exp, exp_dim, dens) in enumerate(test_configs):
            print(f"\n\n{'#'*100}")
            print(f"TEST CONFIG {i+1}/{len(test_configs)}")
            print(f"{'#'*100}")
            
            passed = run_validation_test(
                bs, sl, emb, exp, exp_dim, dens,
                args.rtol, args.atol, args.backward_rtol, args.backward_atol
            )
            all_passed = all_passed and passed
        
        print(f"\n\n{'#'*100}")
        print(f"ALL TESTS RESULT: {'✓ ALL PASSED' if all_passed else '✗ SOME FAILED'}")
        print(f"{'#'*100}")
        
        sys.exit(0 if all_passed else 1)
    else:
        # Single test
        passed = run_validation_test(
            args.batch_size, args.seq_len, args.n_embd,
            args.n_experts, args.expert_dim, args.density,
            args.rtol, args.atol, args.backward_rtol, args.backward_atol
        )
        
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
