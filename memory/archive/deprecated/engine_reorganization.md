# Engine Reorganization: Move to src/models/engines/, Remove CSR Wrappers

> **DEPRECATED** (2025-12): Implementation diverged from this plan. Actual structure in `src/models/engines/` with different file names (engine.py, parallel_experts_manual.py).

**Created**: 2025-10-XX
**Status**: Ready to execute
**Goal**: Move engines to dedicated directory, remove redundant CSR wrappers, one-line backend switching

## New Structure

```
src/models/
├── engines/                     # NEW: Dedicated engines directory
│   ├── __init__.py             # NEW: Exports ExpertEngine (alias), ExpertEngineCSR
│   ├── index_add.py            # RENAMED: from expert_engine.py
│   └── csr.py                  # RENAMED: from expert_engine_csr.py
│
├── gec.py                       # UPDATE: Import from engines
├── gec_shared.py                # UPDATE: Import from engines
├── ec.py, ec_shared.py          # Keep as-is
└── model_base.py                # Keep as-is
```

## Phase 1: Create engines/ and Move Files

### Step 1: Create directory
```bash
mkdir -p src/models/engines/
```

### Step 2: Move and rename
```bash
mv src/models/expert_engine.py src/models/engines/index_add.py
mv src/models/expert_engine_csr.py src/models/engines/csr.py
```

### Step 3: Update docstrings in moved files

**File**: `src/models/engines/index_add.py`
- Class name stays: `ExpertEngine`
- Update module docstring to: "ExpertEngine with index_add aggregation (default backend)"

**File**: `src/models/engines/csr.py`
- Class name stays: `ExpertEngineCSR`
- Update module docstring to: "ExpertEngine with CSR aggregation (token-parallel backend)"

### Step 4: Create `engines/__init__.py`

```python
"""Expert computation engines for GEC.

Default backend uses index_add aggregation.
Alternative CSR backend available for testing.

To switch backend, change the ExpertEngine alias below (one-line change).
"""

from .index_add import ExpertEngine as ExpertEngineIndexAdd
from .csr import ExpertEngineCSR

# Default: index_add backend
ExpertEngine = ExpertEngineIndexAdd

# To switch to CSR backend, uncomment:
# ExpertEngine = ExpertEngineCSR

__all__ = ['ExpertEngine', 'ExpertEngineIndexAdd', 'ExpertEngineCSR']
```

## Phase 2: Remove CSR Wrapper Files

### Step 1: Delete wrappers
```bash
rm src/models/gec_csr.py
rm src/models/gec_shared_csr.py
```

### Step 2: Update `src/models/__init__.py`

Remove these lines:
```python
from .gec_csr import GECMLPCSR
from .gec_shared_csr import GECSharedMLPCSR
```

Remove from `__all__`:
```python
"GECMLPCSR",
"GECSharedMLPCSR",
```

## Phase 3: Update GEC and GECShared Imports

### File: `src/models/gec.py`

Change:
```python
from .expert_engine import ExpertEngine
```

To:
```python
from .engines import ExpertEngine
```

### File: `src/models/gec_shared.py`

Change:
```python
from .expert_engine import ExpertEngine
```

To:
```python
from .engines import ExpertEngine
```

## Phase 4: Update model_base.py

### Remove CSR model types

**File**: `src/models/model_base.py`

**Find and replace all** (use replace_all=True):
```python
# OLD pattern (appears in multiple places)
"gec_shared_csr", "gec_csr"

# Remove these from all lists, result should be:
["dense", "gec", "gec_shared", "gec_shared_capacity", "ec", "ec_shared"]
```

### Remove CSR cases from _get_mlp_class

Delete these lines:
```python
elif self.config.model_type == "gec_shared_csr":
    from .gec_shared_csr import GECSharedMLPCSR
    return GECSharedMLPCSR
elif self.config.model_type == "gec_csr":
    from .gec_csr import GECMLPCSR
    return GECMLPCSR
```

## Phase 5: Update Configs (if any)

### Check for CSR configs
```bash
find configs/ -name "*csr*"
```

If found, either:
- Update to use `model_type: gec` or `gec_shared`
- Move to `configs/archive/`

## Phase 6: Update Documentation

### File: `src/models/README.md`

Add section:
```markdown
## Engine Backends

Expert computation engines in `src/models/engines/`:

- **index_add** (default): Uses PyTorch's index_add for aggregation
- **csr**: Uses custom Triton kernels for token-parallel aggregation

### Switching Backend

Edit `src/models/engines/__init__.py` (one-line change):

```python
# Default
ExpertEngine = ExpertEngineIndexAdd

# To use CSR
ExpertEngine = ExpertEngineCSR
```

All models using ExpertEngine will automatically use the selected backend.
```

### File: `CLAUDE.md`

Update:
```markdown
For implementation details, see `src/models/README.md`.

**Engines**: Located in `src/models/engines/`
- `index_add.py` - Default backend (index_add aggregation)
- `csr.py` - Alternative backend (CSR aggregation)

Switch backend via one-line change in `engines/__init__.py`.
```

## Summary

### Files Created:
- `src/models/engines/__init__.py`

### Files Moved:
- `expert_engine.py` → `engines/index_add.py`
- `expert_engine_csr.py` → `engines/csr.py`

### Files Deleted:
- `gec_csr.py`
- `gec_shared_csr.py`

### Files Updated:
- `gec.py` - Import change
- `gec_shared.py` - Import change
- `__init__.py` - Remove CSR exports
- `model_base.py` - Remove CSR model types
- `README.md` - Document backends
- `CLAUDE.md` - Update reference

### NOT Changed:
- Benchmarks (will be updated by another agent)

## Migration for Users

**Old**:
```python
from src.models import GECMLPCSR
model = GECMLPCSR(config)
```

**New**:
```python
# Edit src/models/engines/__init__.py:
ExpertEngine = ExpertEngineCSR

# Then:
from src.models import GECMLP
model = GECMLP(config)  # Now uses CSR
```
