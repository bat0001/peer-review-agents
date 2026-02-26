"""
Tests for prealloc_all_to_all operation.

Run with:
    CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 test/test_prealloc_all_to_all.py
"""

import torch
import torch.distributed as dist


def setup():
    if not dist.is_initialized():
        dist.init_process_group(backend="nccl")
    rank = dist.get_rank()
    torch.cuda.set_device(rank)
    return rank, dist.get_world_size()


def test_packed_forward():
    """Test packed mode forward only."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")
    from src.ops.prealloc_all_to_all import prealloc_all_to_all

    hidden = 4
    # Rank 0 sends [3 to r0, 2 to r1], Rank 1 sends [2 to r0, 4 to r1]
    if rank == 0:
        input_splits = [[3, 2]]
        output_splits = [[3, 2]]  # recv 3 from r0, 2 from r1 = 5 total
    else:
        input_splits = [[2, 4]]
        output_splits = [[2, 4]]  # recv 2 from r0, 4 from r1 = 6 total

    x = torch.randn(sum(input_splits[0]), hidden, device=device).contiguous()
    out = prealloc_all_to_all([x], output_splits, input_splits, hidden, device, x.dtype)

    assert out.shape == (sum(output_splits[0]), hidden)
    if rank == 0:
        print("[PASS] test_packed_forward")
    dist.barrier()


def test_packed_backward():
    """Test packed mode with backward."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")
    from src.ops.prealloc_all_to_all import prealloc_all_to_all

    hidden = 4
    if rank == 0:
        input_splits = [[3, 2]]
        output_splits = [[3, 2]]
    else:
        input_splits = [[2, 4]]
        output_splits = [[2, 4]]

    x = torch.randn(sum(input_splits[0]), hidden, device=device, requires_grad=True)

    out = prealloc_all_to_all([x], output_splits, input_splits, hidden, device, x.dtype)
    # Add computation to get real gradient (not expanded tensor from sum())
    out = out * 2.0
    loss = out.sum()
    loss.backward()

    assert x.grad is not None
    assert x.grad.shape == x.shape
    if rank == 0:
        print("[PASS] test_packed_backward")
    dist.barrier()


def test_padded_forward():
    """Test padded mode forward - dispatch style."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")
    from src.ops.prealloc_all_to_all import prealloc_all_to_all

    n_experts = 2
    hidden = 4
    max_k = 10

    if rank == 0:
        output_splits = [[3, 2], [4, 3]]  # Expert 0: 5, Expert 1: 7
        input_splits = [[3, 4], [2, 3]]
    else:
        output_splits = [[4, 3], [3, 2]]
        input_splits = [[2, 3], [3, 4]]

    x_list = [torch.randn(sum(input_splits[i]), hidden, device=device).contiguous()
              for i in range(n_experts)]
    recv_offsets = [i * max_k for i in range(n_experts)]

    out = prealloc_all_to_all(x_list, output_splits, input_splits, hidden, device, x_list[0].dtype, recv_offsets)

    # Check gaps are zero
    for i in range(n_experts):
        recv_size = sum(output_splits[i])
        gap_start = recv_offsets[i] + recv_size
        gap_end = recv_offsets[i + 1] if i < n_experts - 1 else out.shape[0]
        if gap_end > gap_start:
            assert torch.allclose(out[gap_start:gap_end], torch.zeros(gap_end - gap_start, hidden, device=device))

    if rank == 0:
        print("[PASS] test_padded_forward")
    dist.barrier()


def test_padded_backward():
    """Test padded mode backward - dispatch backward."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")
    from src.ops.prealloc_all_to_all import prealloc_all_to_all

    n_experts = 2
    hidden = 4
    max_k = 10

    if rank == 0:
        output_splits = [[3, 2], [4, 3]]
        input_splits = [[3, 4], [2, 3]]
    else:
        output_splits = [[4, 3], [3, 2]]
        input_splits = [[2, 3], [3, 4]]

    x_list = [torch.randn(sum(input_splits[i]), hidden, device=device, requires_grad=True)
              for i in range(n_experts)]
    recv_offsets = [i * max_k for i in range(n_experts)]

    out = prealloc_all_to_all(x_list, output_splits, input_splits, hidden, device, x_list[0].dtype, recv_offsets)

    # Simulate expert computation (creates real gradient)
    out = out * 2.0
    # Only sum the real data, not padding
    loss = 0
    for i in range(n_experts):
        recv_size = sum(output_splits[i])
        loss = loss + out[recv_offsets[i]:recv_offsets[i]+recv_size].sum()
    loss.backward()

    for i, x in enumerate(x_list):
        assert x.grad is not None, f"x_list[{i}].grad is None"
        assert x.grad.shape == x.shape

    if rank == 0:
        print("[PASS] test_padded_backward")
    dist.barrier()


def test_round_trip():
    """Test dispatch -> expert -> combine round trip."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")
    from src.ops.prealloc_all_to_all import prealloc_all_to_all

    hidden = 4
    if rank == 0:
        dispatch_input_splits = [[3, 2]]
        dispatch_output_splits = [[3, 2]]
    else:
        dispatch_input_splits = [[2, 4]]
        dispatch_output_splits = [[2, 4]]

    x = torch.randn(sum(dispatch_input_splits[0]), hidden, device=device, requires_grad=True)

    # Dispatch
    tokens = prealloc_all_to_all([x], dispatch_output_splits, dispatch_input_splits,
                                  hidden, device, x.dtype)

    # Expert computation
    h = tokens * 2.0

    # Combine (reverse splits)
    combine_input_splits = dispatch_output_splits
    combine_output_splits = dispatch_input_splits
    final = prealloc_all_to_all([h], combine_output_splits, combine_input_splits,
                                 hidden, device, h.dtype)

    # Check correctness
    assert torch.allclose(final, x * 2.0, atol=1e-5)

    # Backward - add computation to avoid expanded tensor
    loss = (final * 1.0).sum()
    loss.backward()
    assert torch.allclose(x.grad, torch.full_like(x, 2.0), atol=1e-5)

    if rank == 0:
        print("[PASS] test_round_trip")
    dist.barrier()


def test_zero_tokens():
    """Test edge case: some experts receive zero tokens."""
    rank, world_size = setup()
    device = torch.device(f"cuda:{rank}")
    from src.ops.prealloc_all_to_all import prealloc_all_to_all

    n_experts = 2
    hidden = 4

    # Expert 0 gets tokens, Expert 1 gets zero from rank1
    # Rank A input_splits[i][B] == Rank B output_splits[i][A]
    if rank == 0:
        input_splits = [[3, 0], [2, 3]]   # E0: 3→r0, 0→r1; E1: 2→r0, 3→r1
        output_splits = [[3, 2], [2, 0]]  # E0: 3←r0, 2←r1; E1: 2←r0, 0←r1
    else:
        input_splits = [[2, 3], [0, 2]]   # E0: 2→r0, 3→r1; E1: 0→r0, 2→r1
        output_splits = [[0, 3], [3, 2]]  # E0: 0←r0, 3←r1; E1: 3←r0, 2←r1

    x_list = [torch.randn(sum(input_splits[i]), hidden, device=device, requires_grad=True)
              for i in range(n_experts)]

    out = prealloc_all_to_all(x_list, output_splits, input_splits, hidden, device, x_list[0].dtype)

    # Computation and backward
    out = out * 2.0
    out.sum().backward()

    for i, x in enumerate(x_list):
        if x.numel() > 0:
            assert x.grad is not None

    if rank == 0:
        print("[PASS] test_zero_tokens")
    dist.barrier()


def main():
    setup()
    rank = dist.get_rank()
    if rank == 0:
        print("=" * 40)
        print("Testing prealloc_all_to_all")
        print("=" * 40)

    test_packed_forward()
    test_packed_backward()
    test_padded_forward()
    test_padded_backward()
    test_round_trip()
    test_zero_tokens()

    if rank == 0:
        print("=" * 40)
        print("All tests passed!")
        print("=" * 40)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
