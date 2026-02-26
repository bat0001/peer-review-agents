#!/usr/bin/env python3
"""
Quick test to verify eval visualizations work correctly.
Runs GEC model for a few steps and checks that visualization outputs are created.
"""

import sys
from pathlib import Path
import shutil

PYTHON = "/data2/hanchi/miniconda3/envs/nanochat/bin/python3.12"

def main():
    print("=" * 80)
    print("Testing Eval Visualizations")
    print("=" * 80)

    # Clean up any previous test outputs
    test_output = Path("./outputs/test_viz")
    if test_output.exists():
        print(f"\nCleaning up previous test output: {test_output}")
        shutil.rmtree(test_output)

    # Import after cleanup to avoid stale directories
    # Add project root to path (parent of test/ directory)
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from src.config import Config
    from src.trainer import Trainer

    # Create minimal config
    config_dict = {
        "experiment_name": "test_viz",
        "output_dir": "./outputs/test_viz",
        "model": {
            "model_type": "gec",
            "vocab_size": 50257,
            "n_embd": 128,
            "n_layer": 4,
            "n_head": 4,
            "block_size": 256,
            "granularity": 2,
            "expansion": 4,
        },
        "data": {
            "data_path": "/data2/.cache/nanochat/base_data",
            "tokenizer_type": "rustbpe",
            "tokenizer_dir": "/data2/.cache/nanochat/tokenizer",
            "tokenizer_threads": 4,
            "tokenizer_batch_size": 128,
            "nanochat_base_dir": "/data2/.cache/nanochat",
        },
        "training": {
            "total_batch_size": 4096,
            "per_device_batch_size": 4,
            "sequence_length": 256,
            "max_steps": 10,
            "eval_interval": 5,
            "save_interval": 10,
            "plot_interval": 5,  # Generate plots at step 5 and 10
            "enable_visualizations": True,
            "compile_model": False,
            "mixed_precision": False,
        },
        "logging": {
            "use_wandb": False,
            "log_interval": 5,
        }
    }

    print("\nConfig:")
    print(f"  Model: GEC (4 layers, 128 dim)")
    print(f"  Steps: 10")
    print(f"  Eval interval: 5")
    print(f"  Plot interval: 5")
    print(f"  Visualizations: enabled")

    try:
        # Create config and trainer
        config = Config.from_dict(config_dict)
        trainer = Trainer(config, rank=0, world_size=1)

        print("\n" + "=" * 80)
        print("Running training...")
        print("=" * 80)

        # Run training
        trainer.train()

        # Check outputs
        print("\n" + "=" * 80)
        print("Checking visualization outputs...")
        print("=" * 80)

        output_dir = Path(config_dict["output_dir"]) / config_dict["experiment_name"]

        # Check JSON logs
        eval_logs_dir = output_dir / "eval_logs"
        expert_counts = eval_logs_dir / "expert_counts.json"
        weight_percentiles = eval_logs_dir / "weight_percentiles.json"

        print(f"\nJSON logs directory: {eval_logs_dir}")
        if expert_counts.exists():
            print(f"  ✓ {expert_counts.name} exists")
        else:
            print(f"  ✗ {expert_counts.name} missing")
            return 1

        if weight_percentiles.exists():
            print(f"  ✓ {weight_percentiles.name} exists")
        else:
            print(f"  ✗ {weight_percentiles.name} missing")
            return 1

        # Check plots (should be generated at steps 5 and 10)
        viz_dir = output_dir / "visualizations"
        print(f"\nVisualizations directory: {viz_dir}")

        for step in [5, 10]:
            step_dir = viz_dir / f"step_{step}"
            if step_dir.exists():
                print(f"  ✓ step_{step}/ directory exists")

                # Check subdirectories
                subdirs = ["weight_cdf", "loss_by_experts", "cutoff_vs_loss", "entropy_vs_experts"]
                for subdir in subdirs:
                    subdir_path = step_dir / subdir
                    if subdir_path.exists():
                        png_files = list(subdir_path.glob("*.png"))
                        print(f"    ✓ {subdir}/ has {len(png_files)} plot(s)")
                    else:
                        print(f"    ✗ {subdir}/ missing")
            else:
                print(f"  ✗ step_{step}/ directory missing")

        print("\n" + "=" * 80)
        print("✓ Visualization test completed successfully!")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n✗ Test failed with error:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
