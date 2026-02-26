# Remove Bias References for Nanochat Style

**Status**: Completed (archived 2026-02)
**Date**: 2025-10-29

## Context

When switching to nanochat architecture, biases were removed from the base `GECSharedMLP` class in `src/models/gec_shared/shared.py`. However, three subclasses that override `forward_topk()` were not updated and still reference non-existent bias parameters.

## Problem

The following files still reference bias parameters that don't exist:
1. `src/models/gec_shared/add_into_shared.py` - 4 bias refs, 2 activation updates
2. `src/models/gec_shared/add_into_shared_explicit.py` - 4 bias refs, 2 activation updates
3. `src/models/gec_shared/debug_addinto.py` - 6 bias refs, 4 activation updates

This causes `AttributeError: 'AddIntoSharedGECMLP' object has no attribute 'shared_bias1'`

## Nanochat Style Requirements

From `shared.py` (reference implementation):
- **No bias parameters** - All `F.linear()` calls use only weight, no bias
- **ReLU² activation** - Use `F.relu(x).square()` instead of `self.act(x)`
- **2D ParameterLists** - Already correct in all files (no changes needed)

## Changes Required

### File 1: `add_into_shared.py`
**Shared expert (lines 32-34):**
- Line 32: `F.linear(x_flat, self.shared_weight1, self.shared_bias1)` → remove bias arg
- Line 33: `self.act(shared_h)` → `F.relu(shared_h).square()`
- Line 34: `F.linear(shared_h, self.shared_weight2, self.shared_bias2)` → remove bias arg

**Routed experts (lines 71-79):**
- Line 73: Remove entire line `h = h + self.bias1.unsqueeze(1)`
- Line 74: `self.act(h)` → `F.relu(h).square()`
- Line 79: Remove entire line `h = h + self.bias2.unsqueeze(1)`

### File 2: `add_into_shared_explicit.py`
**Shared expert (lines 38-40):**
- Line 38: `F.linear(x_flat, self.shared_weight1, self.shared_bias1)` → remove bias arg
- Line 39: `self.act(shared_h)` → `F.relu(shared_h).square()`
- Line 40: `F.linear(shared_h, self.shared_weight2, self.shared_bias2)` → remove bias arg

**Routed experts (lines 81, 86-87):**
- Line 81: Remove entire line `h = h + self.bias1.unsqueeze(1)`
- Line 82: `self.act(h)` → `F.relu(h).square()`
- Lines 86-87: Remove comment and `h = h + self.bias2.unsqueeze(1).to(h.dtype)`

### File 3: `debug_addinto.py`
**Shared expert (lines 36, 39-42):**
- Line 36: `F.linear(x_flat, self.shared_weight1, self.shared_bias1)` → remove bias arg
- Line 39: `self.act(shared_h)` → `F.relu(shared_h).square()`
- Line 40: Update debug comment "GELU" → "ReLU²"
- Line 42: `F.linear(shared_h, self.shared_weight2, self.shared_bias2)` → remove bias arg

**Routed experts (lines 91-95, 101-102):**
- Line 91: Remove entire line `h = h + self.bias1.unsqueeze(1)`
- Line 92: Remove debug print for bias1
- Line 94: `self.act(h)` → `F.relu(h).square()`
- Line 95: Update debug comment "GELU" → "ReLU²"
- Line 101: Remove entire line `h = h + self.bias2.unsqueeze(1).to(h.dtype)`
- Line 102: Remove debug print for bias2

## Execution Plan

Launch 3 parallel subagents (general-purpose) to fix each file independently:
1. Agent 1: Fix `add_into_shared.py`
2. Agent 2: Fix `add_into_shared_explicit.py`
3. Agent 3: Fix `debug_addinto.py`

## Verification

After fixes, run: `python -m benchmark.mlp.gec_shared` to verify no AttributeError.
