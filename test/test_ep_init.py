#!/usr/bin/env python3
"""Test Expert Parallel (EP) initialization.

Verifies:
1. DP params (router, attention, embeddings, shared_weight) are IDENTICAL across ranks
2. EP params (expert_weight) are DIFFERENT across ranks

Run with: torchrun --nproc_per_node=2 test/test_ep_init.py
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import torch
import torch.distributed as dist

from src.models import BaseGPT, ModelConfig
from src.utils.distributed import compute_init, compute_cleanup, init_model_weights


def test_ep_init():
    """Test EP initialization correctness."""
    # Initialize with EP mode
    ddp, rank, local_rank, world_size, device = compute_init(
        seed=42, expert_parallel=True
    )

    if world_size < 2:
        print("ERROR: Need at least 2 GPUs for EP test. Run with torchrun --nproc_per_node=2")
        return False

    overall_success = True

    for model_type in ["gec", "gec_shared"]:
        if rank == 0:
            print("\n" + "=" * 60)
            print(f"EP init test: model_type={model_type}")
            print("=" * 60)

        # Create model config
        config = ModelConfig(
            n_embd=256,
            n_layer=2,
            n_head=4,
            model_type=model_type,
            granularity=2,
            expansion=4,
            expert_parallel=True,
        )

        # Create and init model
        with torch.device("meta"):
            model = BaseGPT(config)
        model.to_empty(device=device)
        init_model_weights(model, expert_parallel=True)

        # Collect results
        dp_matches = []
        ep_passes = []

        for name, param in model.named_parameters():
            # Gather param from all ranks
            gathered = [torch.zeros_like(param) for _ in range(world_size)]
            dist.all_gather(gathered, param)

            if rank == 0:
                # Check if params match across ranks
                all_same = all(torch.allclose(gathered[0], g, atol=1e-6) for g in gathered[1:])

                if 'expert_weight' in name:
                    if 'expert_weight2' in name:
                        # expert_weight2 is zero-initialized by design
                        all_zero = all(torch.allclose(g, torch.zeros_like(g), atol=1e-6) for g in gathered)
                        if all_same and all_zero:
                            print(f"✓ EP param {name} zero-initialized across ranks")
                            ep_passes.append(True)
                        else:
                            if all_same:
                                print(f"FAIL: EP param {name} identical but non-zero (expected zero init)")
                            else:
                                print(f"FAIL: EP param {name} diverged but expected zero init")
                            ep_passes.append(False)
                    else:
                        # EP params should be DIFFERENT
                        if all_same:
                            print(f"FAIL: EP param {name} is identical across ranks (should differ)")
                            ep_passes.append(False)
                        else:
                            print(f"✓ EP param {name} differs across ranks")
                            ep_passes.append(True)
                else:
                    # DP params should be IDENTICAL
                    if all_same:
                        print(f"✓ DP param {name} identical across ranks")
                        dp_matches.append(True)
                    else:
                        print(f"FAIL: DP param {name} differs across ranks (should be identical)")
                        dp_matches.append(False)

        # Also check buffers (cutoff_ema_raw, cos, sin)
        for name, buffer in model.named_buffers():
            if buffer is None:
                continue
            gathered = [torch.zeros_like(buffer) for _ in range(world_size)]
            dist.all_gather(gathered, buffer)

            if rank == 0:
                all_same = all(torch.allclose(gathered[0], g, atol=1e-6) for g in gathered[1:])
                if all_same:
                    print(f"✓ Buffer {name} identical across ranks")
                    dp_matches.append(True)
                else:
                    print(f"FAIL: Buffer {name} differs across ranks")
                    dp_matches.append(False)

        if rank == 0:
            print("\n" + "-" * 60)
            print("Summary:")
            print(f"  DP params/buffers identical: {sum(dp_matches)}/{len(dp_matches)}")
            print(f"  EP params OK (divergent or zero-init): {sum(ep_passes)}/{len(ep_passes)}")

            success = all(dp_matches) and all(ep_passes)
            if success:
                print("\n✓ EP initialization test PASSED")
            else:
                print("\n✗ EP initialization test FAILED")
            print("-" * 60)

            overall_success = overall_success and success

        dist.barrier()

    return overall_success if rank == 0 else True


if __name__ == "__main__":
    try:
        success = test_ep_init()
    finally:
        compute_cleanup()

    sys.exit(0 if success else 1)
