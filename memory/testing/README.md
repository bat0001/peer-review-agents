# Testing Documentation

This directory documents **critical tests** that protect against regressions and validate core assumptions.

## Philosophy

**Testing is verification, not exploration**
Tests exist to prevent known failure modes and validate that critical properties hold. Every test here documents a real bug that was found or a critical invariant that must be maintained.

## Critical Tests

### Weight Initialization (`test/test_weight_init.py`)

**What it tests:** All model parameters are initialized correctly with expected standard deviations.

**Why it exists:** Caught catastrophic bug where all expert weights were initialized to ZERO due to nanochat's meta-device pattern discarding initial values.

**How to run:**
```bash
# Single GPU
CUDA_VISIBLE_DEVICES=0 python test/test_weight_init.py +experiment=debug

# Multi-GPU (with torchrun)
CUDA_VISIBLE_DEVICES=0,1 torchrun --nproc_per_node=2 test/test_weight_init.py +experiment=debug
```

**Expected output:**
```
Total parameters analyzed: 58
Mismatches: 0
✅ All weight initializations match expected values!
```

**Details:** See `weight_initialization.md`

## Test Categories

### 1. Initialization Tests
- `test/test_weight_init.py` - Verify all parameters initialized with correct std

### 2. Model Tests (via benchmark/)
Per project guidelines, model module testing uses `benchmark/` (benchmarking is testing):
- `benchmark/mlp/` - MLP forward/backward correctness and performance
- `benchmark/permutation/` - Routing operation correctness

### 3. Integration Tests (test/)
All other testing files go in `test/`:
- Future: distributed training tests
- Future: data loading tests
- Future: optimizer tests

## When to Add a Test

**Add a critical test when:**
1. You find a silent bug that could recur (like weight init)
2. You discover a critical invariant that must hold (like zero-init for Muon)
3. You implement a complex feature with non-obvious correctness conditions

**Document in memory/testing/ when:**
- Test protects against a specific failure mode worth remembering
- Test validates important design assumptions
- Future agents need context on why the test exists

## Running All Tests

```bash
# Weight initialization
CUDA_VISIBLE_DEVICES=0 python test/test_weight_init.py +experiment=debug

# MLP correctness (forward/backward modes with both routing types)
CUDA_VISIBLE_DEVICES=0 python -m benchmark.mlp forward --routing-mode topk --tokens 2048 --hidden 256 -G 2 -E 2
CUDA_VISIBLE_DEVICES=0 python -m benchmark.mlp backward --routing-mode topk --tokens 2048 --hidden 256 -G 2 -E 2

# Add more as tests are added...
```

## Test Maintenance

**Tests should:**
- Be fast (use small configs, +experiment=debug)
- Fail loudly (assertions, not warnings)
- Document what they protect against
- Be runnable on single GPU

**Tests should NOT:**
- Replace documentation (document the WHY separately)
- Be slow integration tests (keep them focused)
- Require manual inspection (automated pass/fail)
