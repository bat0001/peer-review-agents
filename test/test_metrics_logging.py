#!/usr/bin/env python3
"""
Test script to validate metrics logging across EC, GEC, and GEC_shared models.
Runs each model type for 100 steps to verify all metrics are collected correctly.
"""

import subprocess
import sys
from pathlib import Path

PYTHON = "/data2/hanchi/miniconda3/envs/gec/bin/python3.12"

# Get project root (parent of test/ directory)
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG = PROJECT_ROOT / "configs/debug_moe.yaml"
TRAIN_SCRIPT = PROJECT_ROOT / "train.py"
MAX_STEPS = 100

model_types = ["ec", "gec", "gec_shared"]

def run_training(model_type: str):
    """Run training for a specific model type."""
    print(f"\n{'='*80}")
    print(f"Testing {model_type.upper()} model")
    print(f"{'='*80}\n")

    cmd = [
        PYTHON, str(TRAIN_SCRIPT),
        "--config", str(CONFIG),
        "--model-type", model_type,
        "--experiment-name", f"test-metrics-{model_type}",
        "--max-steps", str(MAX_STEPS)
    ]

    print(f"Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n✓ {model_type.upper()} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ {model_type.upper()} failed with error code {e.returncode}")
        return False
    except KeyboardInterrupt:
        print(f"\n✗ {model_type.upper()} interrupted by user")
        return False

def main():
    print("Metrics Logging Test")
    print("=" * 80)
    print(f"Config: {CONFIG.relative_to(PROJECT_ROOT)}")
    print(f"Max steps: {MAX_STEPS}")
    print(f"Model types: {', '.join(model_types)}")
    print("=" * 80)

    results = {}
    for model_type in model_types:
        success = run_training(model_type)
        results[model_type] = success

        if not success:
            print("\n⚠️  Test failed, stopping early")
            break

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for model_type, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{model_type:12s} {status}")
    print("=" * 80)

    all_passed = all(results.values())
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
