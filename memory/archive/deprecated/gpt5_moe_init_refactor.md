# MoE Initialization Refactor – Plan

**Status**: ⚠️ ARCHIVED - Superseded
**Date**: 2025-10-09
**Superseded by**: memory/plans/moe_init_scaling.md (2025-10-17)
**Note**: Earlier iteration of MoE initialization plan. Newer version is more concise and better structured.

---

**Original Plan:**

**Author:** Codex (GPT-5)
**Goal:** Replace all hard-coded MoE MLP/router normal initializations `std=0.02` with the compute-aware rule `std = 0.02 * sqrt(E)` while keeping the implementation clean, centralized, and backwards compatible across GEC/EC variants (including Triton and legacy paths).

---

## 1. Current State

- Every MoE module manually creates its own `nn.Parameter(torch.randn(...) * 0.02)` tensors:
  - `src/models/gec/{gec.py, segmented.py, triton.py, triton1.py, reference.py}`
  - `src/models/ec.py`
  - `src/models/gec_shared/shared.py`
  - Vendored/legacy modules: `legacy/legacy_mod/{mod.py, mode.py}`, `scattermoe/*`
  - Tests mirror the constant (`scattermoe/tests/test_mlp.py`)
- The constant appears directly in constructors for router weights, expert FC weights, and shared-expert layers. This duplicates logic and makes future changes tedious.

Configuration recap:

- `ModelConfig.expansion` encodes **E**.  
- `ModelConfig.granularity` encodes **G** with `n_experts = G × E` (except shared variant +1).  
- Some legacy configs may bypass the new notation and set `n_experts` manually; we must infer E as `n_experts / granularity` when possible.

---

## 2. Requirements & Constraints

1. **Uniform rule:** All MoE/GEC routers and expert MLPs (including shared expert) must use `std = 0.02 * sqrt(E_effective)`, where `E_effective` is:
   - `config.expansion` for modern configs.
   - `config.n_experts / config.granularity` for legacy explicit expert counts (integer check).
   - For GEC-shared: use routed expert expansion (`(config.n_experts - 1) / config.granularity`).
2. **Coverage:** Apply to PyTorch, Triton, segmented, reference, and legacy code; tests should reference the helper instead of hard-coded constants.
3. **Clarity:** Refactor should reduce boilerplate; callers should never repeat `torch.randn(...)*constant`.
4. **Safety:** Provide validation/logical errors if E cannot be inferred (e.g., `granularity` missing). Keep dense models untouched.
5. **Minimal runtime overhead:** Rely on eager init via `nn.init.normal_`, no extra allocations beyond current pattern.

---

## 3. Proposed Structure

### 3.1 New Helper Module

Create `src/models/init_utils.py` to keep initialization logic decoupled from the large `model_base.py`:

```
src/models/
├── __init__.py
├── init_utils.py   # <─ new
├── model_base.py
├── gec/
│   ├── gec.py
│   ├── segmented.py
│   ├── triton.py
│   ├── triton1.py
│   └── reference.py
├── ec.py
└── gec_shared/
    └── shared.py
```

### 3.2 Helper API

```python
# src/models/init_utils.py
import math
from typing import Sequence, Optional
import torch
import torch.nn as nn

def infer_expansion(config: "ModelConfig", *, routed_only: bool = False) -> float:
    """
    Return E for MoE weight initialization.
    routed_only=True subtracts the shared expert for GEC-shared.
    Raises ValueError if expansion cannot be inferred.
    """

def moe_init_std(expansion: float) -> float:
    return 0.02 * math.sqrt(expansion)

def moe_normal_parameter(
    shape: Sequence[int],
    *,
    config: "ModelConfig",
    routed_only: bool = False,
    dtype: Optional[torch.dtype] = None,
    device: Optional[torch.device] = None,
) -> nn.Parameter:
    std = moe_init_std(infer_expansion(config, routed_only=routed_only))
    tensor = torch.empty(*shape, dtype=dtype, device=device)
    nn.init.normal_(tensor, mean=0.0, std=std)
    return nn.Parameter(tensor)
```

Notes:
- `infer_expansion` handles both modern (`config.expansion`) and legacy (`config.n_experts` & `granularity`) setups.
- `routed_only` ensures shared expert init uses the same expansion as routed experts.
- Keep docstrings + type hints for clarity.

### 3.3 Usage in MoE Modules

Example conversion inside `GECMLP.__init__`:

```python
from ..init_utils import moe_normal_parameter

self.router_w = moe_normal_parameter(
    (config.n_embd, config.n_experts),
    config=config,
)
self.weight1 = moe_normal_parameter(
    (config.n_experts, config.expert_dim, config.n_embd),
    config=config,
)
self.weight2 = moe_normal_parameter(
    (config.n_experts, config.n_embd, config.expert_dim),
    config=config,
)
```

Shared expert:

```python
self.shared_weight1 = moe_normal_parameter(
    (config.shared_expert_dim, config.n_embd),
    config=config,
    routed_only=True,  # discount shared slot when computing E
)
```

Legacy modules (`legacy_mod`, `scattermoe`):
- Import the same helper; if those files avoid circular imports, keep path as `from ...init_utils import ...`.
- Where config objects differ, add small adaptor functions to pass expansion explicitly (`moe_normal_parameter(..., config_like=SimpleNamespace(expansion=legacy_expansion, granularity=legacy_granularity))`).

Tests:
- Update fixtures to call `moe_init_std(expansion)` or simply rely on production constructors; avoid hard-coded constants.

---

## 4. Implementation Steps

1. **Scaffold helper module**
   - Create `src/models/init_utils.py`.
   - Implement `infer_expansion`, `moe_init_std`, `moe_normal_parameter`.
   - Ensure imports use forward references to avoid circular dependency (`typing.TYPE_CHECKING`).

2. **Refactor core GEC/EC modules**
   - Replace `torch.randn(...)*0.02` with `moe_normal_parameter`.
   - Cover router weights, expert weights, shared expert weights.
   - Preserve bias initializations (`torch.zeros`) unchanged.

3. **Handle Triton / segmented / reference variants**
   - Apply the same helper imports.
   - Confirm shapes match expectations (some use intermediate flattening).

4. **Legacy/Vendored updates**
   - Evaluate `legacy_mod` + `scattermoe` dependencies:
     - If they instantiate their own `config` dataclass, compute expansion `legacy_n_experts / legacy_granularity`.
     - Optionally expose helper overload `moe_normal_parameter_from_std(std: float, shape: Sequence[int])` if config coupling is awkward.
   - Document any divergence in comments.

5. **Tests & Fixtures**
   - Adjust `scattermoe/tests/test_mlp.py` to align with new std.
   - Add regression test under `tests/models/` verifying parameter std uses `0.02 * sqrt(expansion)` (sample by computing sample std of initial weights or check `weight.std()` ~ expected within tolerance).

6. **Cleanup & Validation**
   - `rg "0\.02"` to confirm no MoE weight init still uses the constant.
   - Run targeted unit tests (`pytest tests/models/test_gec.py`, etc.).
   - Document observed diffs / instructions for future agents (update relevant README if needed).

---

## 5. Edge Cases / Questions

- **Non-integer expansion**: if `(n_experts / granularity)` is not integer, raise a descriptive error (signals misconfigured model).  
- **Shared expert presence**: ensure `routed_only=True` handles the single shared expert subtraction; verify for `granularity=2` minimal setups.  
- **Legacy scattermoe**: confirm expansion inference; if missing data, fall back to user-supplied argument or keep legacy constant (document reasoning).  
- **Initialization order**: helpers must align with `torch.set_default_dtype`; create tensors with explicit dtype/device when parent module passes them.

Open question to confirm with maintainers (if needed): should router weights use the same scaling as expert weights? Requirements imply **all MoE MLP linear weights**, so plan treats router and expert layers identically.

---

## 6. Verification Checklist

- [ ] `src/models/init_utils.py` implemented with tests.
- [ ] All GEC/EC variants import helper and no longer use literal `0.02`.
- [ ] Shared expert + routed experts use correct `E`.
- [ ] Legacy modules updated or intentionally exempt (documented).
- [ ] Unit test confirming expected std passes.
- [ ] `rg "0\.02"` only finds unrelated files/logs.
- [ ] Diff reviewed for clarity; no unintended formatting changes.
- [ ] Update `memory/plans` status when implementation completes (archive plan or move to completed).

---

### Quick Reference (expected std values)

| Expansion (E) | Std |
|---------------|------|
| 1             | 0.02 |
| 2             | 0.028284... |
| 4             | 0.04 |
| 8             | 0.056568... |

*Useful for manual verification during testing.*

