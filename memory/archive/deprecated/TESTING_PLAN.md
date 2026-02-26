# nanochat Integration Testing Plan

## Overview
Testing the integration of nanochat techniques (Muon optimizer, RoPE, ReLU², etc.) into nano_gec.

## Test Environment
- CUDA available: Required
- Python: 3.12.11
- Environment: gec

## Test Suite

### Phase 1: Module Imports (Smoke Tests)
**Goal**: Verify no syntax errors, all imports work

1. Import model_base and verify helper functions
2. Import optimizers module
3. Import distributed utils
4. Import new data_loader

**Expected**: No import errors

---

### Phase 2: Model Creation
**Goal**: Verify models initialize correctly with new architecture

1. **Dense Model**
   - Create ModelConfig with model_type="dense"
   - Initialize BaseGPT
   - Verify parameters (no wpe, no bias, untied embeddings)
   - Check RoPE buffers exist

2. **GEC_shared Model**
   - Create ModelConfig with model_type="gec_shared"
   - Initialize BaseGPT
   - Verify GEC parameters (no bias)
   - Check expert architecture

**Expected**: Models initialize without errors, parameter counts reasonable

---

### Phase 3: Forward Pass
**Goal**: Verify forward pass works with new architecture

1. **Dense Forward**
   - Create dummy input (B=2, T=128)
   - Run model.forward()
   - Verify output shapes
   - Check loss computation

2. **GEC Forward**
   - Create dummy input (B=2, T=128)
   - Run model.forward()
   - Verify output shapes
   - Check routing metrics

**Expected**: Forward pass completes, output shapes correct, no NaN/Inf

---

### Phase 4: Optimizer Creation
**Goal**: Verify hybrid optimizer setup works

1. Create model
2. Call create_hybrid_optimizer()
3. Verify parameter separation (2D→Muon, embeddings→AdamW)
4. Check initial LRs are set correctly

**Expected**: Two optimizers created, parameters split correctly

---

### Phase 5: Training Step
**Goal**: Verify training loop mechanics work

1. Create model, optimizers, dummy data
2. Run forward pass
3. Run backward pass
4. Run optimizer.step()
5. Verify gradients flow correctly
6. Check parameter updates

**Expected**: Training step completes, loss decreases over a few steps

---

### Phase 6: Integration Test
**Goal**: Verify full training loop with real config

1. Run training with +experiment=debug for 10 steps
2. Check:
   - Config loading works
   - Data loader produces batches
   - Both optimizers step
   - Logging works
   - No crashes

**Expected**: Training runs for 10 steps without errors

---

### Phase 7: Multi-MLP Test
**Goal**: Verify all MLP types work

1. Test dense
2. Test gec
3. Test gec_shared
4. Test ec

**Expected**: All MLP types initialize and run forward pass

---

## Success Criteria

✅ All imports successful
✅ Models initialize with correct architecture
✅ Forward pass produces valid outputs
✅ Optimizers created and step correctly
✅ Training loop completes 10 steps
✅ All MLP types functional

## Failure Handling

If any test fails:
1. Document the error
2. Fix the issue
3. Re-run affected tests
4. Update this document with findings
