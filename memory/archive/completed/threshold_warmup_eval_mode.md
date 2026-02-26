# Threshold Warmup Eval Mode Bug — Plan (2026-01-19)

## Summary
Eval is using `topk` during threshold warmup because routing precedence prefers `routing_mode` over `model.eval()`. When warmup sets `routing_mode='topk'`, eval inherits it and never reaches threshold routing.

This plan flips precedence so **eval always uses threshold**, and then simplifies the routing logic in three concrete ways (detailed below). It also keeps the API aligned with docs (or simplifies it if we decide to drop `None` support).

---

## Discovery (Code References)

### 1) Warmup forces `topk`, overriding eval behavior
`train.py` currently pins `routing_mode='topk'` whenever warmup is enabled:
```python
# train.py
if config.training.threshold_warmup_steps >= 0:
    orig_model.set_routing_mode('topk')
    print0(f"Threshold training enabled: switching to threshold at step {config.training.threshold_warmup_steps}")
```
Because `routing_mode` is an explicit override, eval continues using `topk` even after `model.eval()` is set.

### 2) Auto-switch logic lives inside GEC/Shared forward
Both `GECMLP` and `GECSharedMLP` check `routing_mode` before `self.training`:
```python
# src/models/gec.py
if self.routing_mode is None:
    mode = 'topk' if self.training else 'threshold'
else:
    mode = self.routing_mode
```
So any explicit `routing_mode` (like `'topk'`) forces eval to stay in topk.

### 3) `set_routing_mode(None)` is documented but not implemented
Docs claim `set_routing_mode(None)` restores auto mode, but code rejects `None`:
```python
# src/models/model_base.py
def set_routing_mode(self, mode: str):
    assert mode in ['topk', 'threshold']
```
This makes it impossible to revert to auto without touching MLP internals.

### 4) Capacity is already disabled during eval/inference (verified)
- `src/models/engines/engine.py`: capacity logic is only under `if self.training:`
- `src/models/engines/parallel_experts_manual.py`: same pattern; eval uses `k_actual = above_counts` with no clamp
No code changes are needed for capacity in eval.

---

## Proposed Fix (Option 3: eval wins)

### Option 1 — Low risk simplification (safe cleanup)
**Goal**: keep existing API, just simplify routing logic and warmup.

**Implementation details**
- **`src/models/gec.py`, `src/models/gec_shared.py`**: inline routing dispatch and drop the `mode` variable.
  ```python
  if not self.training:
      return self.engine.forward_threshold(...)
  if self.routing_mode == 'threshold':
      return self.engine.forward_threshold(...)
  return self.engine.forward_topk(...)
  ```
- **`train.py`**: remove the warmup pin to topk.
  ```python
  # delete this line
  # orig_model.set_routing_mode('topk')
  ```
  Keep the warmup switch:
  ```python
  if step == config.training.threshold_warmup_steps and config.training.threshold_warmup_steps >= 0:
      orig_model.set_routing_mode('threshold')
  ```
- **`src/models/model_base.py` + docs**: keep `set_routing_mode(None)` support (doc‑aligned), but note it only affects training now that eval is fixed to threshold.

**Why low risk**: no breaking API changes; just removes redundant logic.

---

### Option 2 — Medium risk simplification (reduce `None` branching)
**Goal**: keep `None` in the API but normalize it internally to reduce branches.

**Implementation details**
- **`src/models/gec.py`, `src/models/gec_shared.py`**: same inline dispatch as Option 1 (eval always threshold).
- **`src/models/model_base.py`**: accept `None` but coerce to `'topk'` internally.
  ```python
  def set_routing_mode(self, mode: Optional[str]):
      if mode is None:
          mode = 'topk'
      assert mode in ['topk', 'threshold']
      ...
  ```
- **`src/models/README.md`, `configs/README.md`**: clarify that `None` means “training defaults to topk”; eval is always threshold.

**Why medium risk**: subtle behavior change if someone expected `None` to be a distinct state (but eval precedence already removes that).

---

### Option 3 — High impact simplification (drop `None`)
**Goal**: remove `None` from routing mode entirely for a simpler API.

**Implementation details**
- **`src/models/model_base.py`**: remove `None` handling; enforce only `'topk' | 'threshold'`.
- **`src/models/model_base.py` ModelConfig**: set `routing_mode: str = "topk"` (no Optional) and drop any `None`-specific validation.
- **`src/models/gec.py`, `src/models/gec_shared.py`**: delete the `routing_mode is None` branch entirely; keep the direct dispatch (eval always threshold).
- **`train.py`**: delete any references that rely on `None` as “auto”; warmup becomes a single explicit switch to threshold.
- **Docs** (`src/models/README.md`, `configs/README.md`): remove `None` examples and “auto” wording; state that routing_mode only affects training and eval is always threshold.
- **Tests**: update any tests that expect eval+topk to be possible (e.g., switch those to `model.train()` when testing topk).
- **Any call sites**: replace `set_routing_mode(None)` with `set_routing_mode('topk')`; remove type hints/Optional usage around routing_mode.
- **Config validation** (`src/config.py`): if there is any logic expecting `routing_mode is None`, simplify it to accept only explicit strings.
 - **Config comments/examples**: update `configs/mlp/gec_shared.yaml` and `configs/mlp/ec_shared.yaml` (remove “null/auto” comments) and any README snippets that show `routing_mode: null`.
 - **Docs snippets**: remove the “Auto‑Switching (Default)” section in `src/models/README.md` and the `set_routing_mode(None)` example; replace with explicit training‑only description.
 - **Tests to re‑target topk**: `test/test_refactored_models.py` should set `model.train()` when exercising topk; keep eval for threshold only. If any test relies on `model.eval()` with `routing_mode='topk'`, update to `model.train()` or explicitly call `forward_topk()` via engine.

**Why high impact**: breaking change for any code/configs relying on `None`.

---

### Tests (small regression guard)
Add or extend a small test to ensure:
- eval uses threshold even when `routing_mode='topk'`
- warmup switch still flips training to threshold at the configured step

Likely location: `test/test_refactored_models.py` (lightweight CPU test).

---

## Expected Behavior After Fix
- Eval **always** uses `threshold` regardless of `routing_mode`.
- Training uses:
  - `topk` when `routing_mode` is `None`
  - The explicit `routing_mode` when set
- Warmup no longer forces eval into topk even if train.py pins `routing_mode='topk'`.

---

## Validation (Optional)
- `pytest test/test_refactored_models.py`
- (If desired) a short debug run with `+experiment=debug` to confirm eval routing metrics shift when warmup is active.
