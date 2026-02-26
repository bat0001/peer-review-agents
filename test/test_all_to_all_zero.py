"""
Test all_to_all_single with zero-sized splits.

Verifies that torch.distributed.all_to_all_single correctly handles:
1. Some ranks sending zero data to some peers
2. Some ranks receiving zero data from some peers
3. A rank receiving zero data from everyone

Run with: CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 test/test_all_to_all_zero.py
"""

import os
import torch
import torch.distributed as dist


def setup():
    dist.init_process_group(backend="nccl")
    rank = dist.get_rank()
    torch.cuda.set_device(rank)
    return rank


def teardown():
    dist.destroy_process_group()


def test_partial_zero_sends():
    """Test case: Rank 0 sends 0 items to Rank 1, but Rank 1 sends items to Rank 0."""
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    device = torch.device(f"cuda:{rank}")

    print(f"\n[Rank {rank}] === Test: Partial Zero Sends ===")

    hidden_dim = 8

    if rank == 0:
        # Rank 0: sends 5 to self, 0 to Rank 1
        input_data = torch.arange(5 * hidden_dim, dtype=torch.float32, device=device).reshape(5, hidden_dim)
        input_splits = [5, 0]
        # Expects 5 from self, 3 from Rank 1
        output_splits = [5, 3]
    else:
        # Rank 1: sends 3 to Rank 0, 2 to self
        input_data = torch.arange(5 * hidden_dim, dtype=torch.float32, device=device).reshape(5, hidden_dim) + 100
        input_splits = [3, 2]
        # Expects 0 from Rank 0, 2 from self
        output_splits = [0, 2]

    total_output = sum(output_splits)
    output_data = torch.empty(total_output, hidden_dim, dtype=torch.float32, device=device)

    print(f"[Rank {rank}] input_splits={input_splits}, output_splits={output_splits}")
    print(f"[Rank {rank}] input shape={input_data.shape}, output shape={output_data.shape}")

    dist.all_to_all_single(
        output_data, input_data,
        output_split_sizes=output_splits,
        input_split_sizes=input_splits
    )

    print(f"[Rank {rank}] output shape after all_to_all: {output_data.shape}")
    print(f"[Rank {rank}] output[:2]:\n{output_data[:2]}")

    # Verify correctness
    if rank == 0:
        # Should have: 5 rows from self (0-39 range), 3 rows from Rank 1 (100+ range)
        assert output_data.shape == (8, hidden_dim), f"Expected (8, {hidden_dim}), got {output_data.shape}"
        # First 5 rows from self
        assert output_data[0, 0].item() == 0.0, f"First element should be 0, got {output_data[0, 0].item()}"
        # Next 3 rows from Rank 1 (which sent its first 3 rows)
        assert output_data[5, 0].item() == 100.0, f"Row 5 should start with 100, got {output_data[5, 0].item()}"
    else:
        # Should have: 0 rows from Rank 0, 2 rows from self
        assert output_data.shape == (2, hidden_dim), f"Expected (2, {hidden_dim}), got {output_data.shape}"
        # These 2 rows are what Rank 1 sent to itself (rows 3-4 of its input, i.e., the last 2 rows)
        # input_data for rank 1 starts at 100, rows 3-4 start at 100 + 3*8 = 124
        expected_start = 100 + 3 * hidden_dim
        assert output_data[0, 0].item() == expected_start, f"Expected {expected_start}, got {output_data[0, 0].item()}"

    print(f"[Rank {rank}] PASSED: Partial Zero Sends")
    dist.barrier()


def test_receive_zero_from_all():
    """Test case: One rank receives zero data from everyone."""
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    device = torch.device(f"cuda:{rank}")

    print(f"\n[Rank {rank}] === Test: Receive Zero From All ===")

    hidden_dim = 8

    if rank == 0:
        # Rank 0: sends 5 to self, 0 to Rank 1
        input_data = torch.arange(5 * hidden_dim, dtype=torch.float32, device=device).reshape(5, hidden_dim)
        input_splits = [5, 0]
        # Expects 5 from self, 0 from Rank 1
        output_splits = [5, 0]
    else:
        # Rank 1: sends 0 to Rank 0, 0 to self (sends nothing to anyone)
        input_data = torch.empty(0, hidden_dim, dtype=torch.float32, device=device)
        input_splits = [0, 0]
        # Expects 0 from everyone
        output_splits = [0, 0]

    total_output = sum(output_splits)
    output_data = torch.empty(total_output, hidden_dim, dtype=torch.float32, device=device)

    print(f"[Rank {rank}] input_splits={input_splits}, output_splits={output_splits}")
    print(f"[Rank {rank}] input shape={input_data.shape}, output shape={output_data.shape}")

    dist.all_to_all_single(
        output_data, input_data,
        output_split_sizes=output_splits,
        input_split_sizes=input_splits
    )

    print(f"[Rank {rank}] output shape after all_to_all: {output_data.shape}")

    if rank == 0:
        assert output_data.shape == (5, hidden_dim)
        assert output_data[0, 0].item() == 0.0
    else:
        # Rank 1 should have an empty tensor
        assert output_data.shape == (0, hidden_dim), f"Expected (0, {hidden_dim}), got {output_data.shape}"
        assert output_data.numel() == 0

    print(f"[Rank {rank}] PASSED: Receive Zero From All")
    dist.barrier()


def test_alternating_zeros():
    """Test case: Ranks only send to themselves (no cross-rank communication)."""
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    device = torch.device(f"cuda:{rank}")

    print(f"\n[Rank {rank}] === Test: Alternating Zeros (Self-Only) ===")

    hidden_dim = 8
    num_items = 4

    # Each rank sends only to itself
    input_data = torch.arange(num_items * hidden_dim, dtype=torch.float32, device=device).reshape(num_items, hidden_dim) + rank * 1000

    # Only send to self
    input_splits = [0] * world_size
    input_splits[rank] = num_items

    # Only receive from self
    output_splits = [0] * world_size
    output_splits[rank] = num_items

    total_output = sum(output_splits)
    output_data = torch.empty(total_output, hidden_dim, dtype=torch.float32, device=device)

    print(f"[Rank {rank}] input_splits={input_splits}, output_splits={output_splits}")

    dist.all_to_all_single(
        output_data, input_data,
        output_split_sizes=output_splits,
        input_split_sizes=input_splits
    )

    # Output should exactly match input (sent to self, received from self)
    assert torch.allclose(output_data, input_data), "Self-send should return same data"

    print(f"[Rank {rank}] PASSED: Alternating Zeros")
    dist.barrier()


def test_empty_tensor_input():
    """Test case: Handle empty tensor inputs correctly."""
    rank = dist.get_rank()
    device = torch.device(f"cuda:{rank}")

    print(f"\n[Rank {rank}] === Test: Empty Tensor Input ===")

    hidden_dim = 8

    # Both ranks send empty tensors
    input_data = torch.empty(0, hidden_dim, dtype=torch.float32, device=device)
    input_splits = [0, 0]
    output_splits = [0, 0]

    output_data = torch.empty(0, hidden_dim, dtype=torch.float32, device=device)

    print(f"[Rank {rank}] input shape={input_data.shape}, output shape={output_data.shape}")

    dist.all_to_all_single(
        output_data, input_data,
        output_split_sizes=output_splits,
        input_split_sizes=input_splits
    )

    assert output_data.shape == (0, hidden_dim)
    assert output_data.numel() == 0

    print(f"[Rank {rank}] PASSED: Empty Tensor Input")
    dist.barrier()


def test_asymmetric_distribution():
    """Test case: Highly asymmetric distribution (one rank gets everything)."""
    rank = dist.get_rank()
    device = torch.device(f"cuda:{rank}")

    print(f"\n[Rank {rank}] === Test: Asymmetric Distribution ===")

    hidden_dim = 8

    if rank == 0:
        # Rank 0 sends everything to Rank 1
        input_data = torch.arange(10 * hidden_dim, dtype=torch.float32, device=device).reshape(10, hidden_dim)
        input_splits = [0, 10]
        # Receives nothing
        output_splits = [0, 0]
    else:
        # Rank 1 sends everything to Rank 1 (self)
        input_data = torch.arange(5 * hidden_dim, dtype=torch.float32, device=device).reshape(5, hidden_dim) + 1000
        input_splits = [0, 5]
        # Receives 10 from Rank 0, 5 from self
        output_splits = [10, 5]

    total_output = sum(output_splits)
    output_data = torch.empty(total_output, hidden_dim, dtype=torch.float32, device=device)

    print(f"[Rank {rank}] input_splits={input_splits}, output_splits={output_splits}")
    print(f"[Rank {rank}] input shape={input_data.shape}, output shape={output_data.shape}")

    dist.all_to_all_single(
        output_data, input_data,
        output_split_sizes=output_splits,
        input_split_sizes=input_splits
    )

    print(f"[Rank {rank}] output shape after all_to_all: {output_data.shape}")

    if rank == 0:
        assert output_data.shape == (0, hidden_dim)
    else:
        assert output_data.shape == (15, hidden_dim)
        # First 10 rows from Rank 0 (values 0-79)
        assert output_data[0, 0].item() == 0.0
        # Next 5 rows from self (values 1000+)
        assert output_data[10, 0].item() == 1000.0

    print(f"[Rank {rank}] PASSED: Asymmetric Distribution")
    dist.barrier()


def main():
    rank = setup()

    print(f"\n{'='*60}")
    print(f"[Rank {rank}] Starting all_to_all_single zero-data tests")
    print(f"[Rank {rank}] World size: {dist.get_world_size()}")
    print(f"{'='*60}")

    try:
        test_partial_zero_sends()
        test_receive_zero_from_all()
        test_alternating_zeros()
        test_empty_tensor_input()
        test_asymmetric_distribution()

        dist.barrier()
        if rank == 0:
            print(f"\n{'='*60}")
            print("ALL TESTS PASSED!")
            print(f"{'='*60}\n")
    finally:
        teardown()


if __name__ == "__main__":
    main()
