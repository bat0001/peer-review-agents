# 2D Parameter Conversion Guide

## Goal
Convert all MoE MLP implementations from 3D weight tensors to ParameterList of 2D tensors, following the pattern in `src/models/gec_shared/shared_2d.py`.

## Why?
The 2D parameter structure enables per-expert optimizer states (e.g., DistMuon) while maintaining efficient batched computation through dynamic stacking.

## Reference Implementation
See `src/models/gec_shared/shared_2d.py` (GECSharedMLP2D) for the complete pattern.

## Conversion Pattern

### 1. Modify `__init__` Method

**Before:**
```python
self.weight1 = nn.Parameter(torch.empty(n_experts, expert_dim, n_embd))
self.weight2 = nn.Parameter(torch.empty(n_experts, n_embd, expert_dim))
```

**After:**
```python
# Replace 3D weight tensors with ParameterList of 2D tensors
self.expert_weight1 = nn.ParameterList([
    nn.Parameter(torch.empty(expert_dim, n_embd))
    for _ in range(n_experts)
])
self.expert_weight2 = nn.ParameterList([
    nn.Parameter(torch.empty(n_embd, expert_dim))
    for _ in range(n_experts)
])

# Remove old 3D parameters (if replacing in-place, not needed if subclass)
# delattr(self, 'weight1')
# delattr(self, 'weight2')
```

**Note:** Use `torch.empty()` since `init_weights()` will initialize them properly.

### 2. Add `state_dict()` Method

Add this method to convert 2D → 3D for checkpoint compatibility:

```python
def state_dict(self, *args, **kwargs):
    """Convert 2D parameters back to 3D format for compatibility."""
    state = super().state_dict(*args, **kwargs)

    # Convert expert_weight1/2 ParameterList to weight1/2 3D tensors
    expert_weight1_keys = [k for k in state.keys() if k.startswith('expert_weight1.')]
    expert_weight2_keys = [k for k in state.keys() if k.startswith('expert_weight2.')]

    if expert_weight1_keys:
        weight1_list = [state.pop(f'expert_weight1.{i}') for i in range(len(expert_weight1_keys))]
        state['weight1'] = torch.stack(weight1_list)

    if expert_weight2_keys:
        weight2_list = [state.pop(f'expert_weight2.{i}') for i in range(len(expert_weight2_keys))]
        state['weight2'] = torch.stack(weight2_list)

    return state
```

### 3. Add `load_state_dict()` Method

Add this method to convert 3D → 2D when loading checkpoints:

```python
def load_state_dict(self, state_dict, strict=True, assign=False):
    """Convert 3D parameters to 2D format before loading."""
    state_dict = state_dict.copy()  # Don't modify the input

    # Convert weight1/2 3D tensors to expert_weight1/2 ParameterList
    if 'weight1' in state_dict:
        weight1_3d = state_dict.pop('weight1')
        for i in range(weight1_3d.shape[0]):
            state_dict[f'expert_weight1.{i}'] = weight1_3d[i]

    if 'weight2' in state_dict:
        weight2_3d = state_dict.pop('weight2')
        for i in range(weight2_3d.shape[0]):
            state_dict[f'expert_weight2.{i}'] = weight2_3d[i]

    return super().load_state_dict(state_dict, strict=strict, assign=assign)
```

### 4. Update Forward Methods

Find where weights are used in batched operations (usually `torch.bmm` or `F.linear`).

**Before:**
```python
# Direct use of 3D tensors
h = torch.bmm(x_permuted, self.weight1.transpose(1, 2))
h = torch.bmm(h, self.weight2.transpose(1, 2))
```

**After:**
```python
# Stack 2D parameters to 3D before batched computation
weight1_3d = torch.stack([w for w in self.expert_weight1])
weight2_3d = torch.stack([w for w in self.expert_weight2])

h = torch.bmm(x_permuted, weight1_3d.transpose(1, 2))
h = torch.bmm(h, weight2_3d.transpose(1, 2))
```

### 5. Update `_expert_forward()` Method (if exists)

If the class has a per-expert forward method:

**Before:**
```python
def _expert_forward(self, x: torch.Tensor, expert_idx: int) -> torch.Tensor:
    h = F.linear(x, self.weight1[expert_idx])
    h = F.relu(h).square()
    h = F.linear(h, self.weight2[expert_idx])
    return h
```

**After:**
```python
def _expert_forward(self, x: torch.Tensor, expert_idx: int) -> torch.Tensor:
    h = F.linear(x, self.expert_weight1[expert_idx])
    h = F.relu(h).square()
    h = F.linear(h, self.expert_weight2[expert_idx])
    return h
```

## GEC_shared Variants: Special Case

For `GECSharedMLP` and its children, there are **both** routed expert weights AND shared expert weights:

**Routed experts** (convert to 2D ParameterList):
- `weight1` → `expert_weight1`
- `weight2` → `expert_weight2`

**Shared expert** (keep as 2D parameters):
- `shared_weight1` (already 2D)
- `shared_weight2` (already 2D)

## Inheritance Strategy

When converting base classes:
1. **Base class** (e.g., GECMLP, GECSharedMLP): Apply full conversion
2. **Child classes** (e.g., GECMLPTrainableThreshold):
   - Check if they override `__init__` and recreate weight tensors
   - If yes, apply the same conversion
   - If no, they inherit the 2D behavior automatically

## Files to Convert

### Phase 1: Independent Base Classes (can be done in parallel)
- `src/models/gec/gec.py` (GECMLP)
- `src/models/gec/reference.py` (GECMLPReference)
- `src/models/gec/triton.py` (GECTritonMLP)
- `src/models/gec/triton1.py` (GECTritonMLP)
- `src/models/gec/segmented.py` (GECSegmentedMLP)
- `src/models/ec.py` (ECMLP)

### Phase 2: GEC_shared Base
- `src/models/gec_shared/shared.py` (GECSharedMLP)

### Phase 3: Child Classes (check for weight overrides)
- `src/models/gec/gec_trainable_threshold.py` (inherits GECMLP)
- `src/models/gec_shared/shared_trainable_threshold.py` (inherits GECSharedMLP)
- `src/models/gec_shared/add_into_shared.py` (inherits GECSharedMLP)
- `src/models/gec_shared/add_into_shared_explicit.py` (inherits GECSharedMLP)
- `src/models/gec_shared/debug_addinto.py` (inherits GECSharedMLP)
- `src/models/ec_shared.py` (inherits GECSharedMLP)

## Testing After Conversion

After converting files, verify:
1. The class still initializes without errors
2. Forward pass works (shapes match)
3. Checkpoint save/load works (3D ↔ 2D conversion)
4. Weight initialization still works (`test/test_weight_init.py`)

## Cleanup

After all conversions:
- Remove `src/models/gec_shared/shared_2d.py` (merge into `shared.py`)
