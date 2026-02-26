# Plan: Add aux_error load balance mode for token-choice MoE

## Goal
Add a new `load_balance_method="aux_error"` for token-choice models that computes
`aux_loss = sum((f - target) * p)` while keeping the existing `aux` behavior
unchanged. Keep the metric key as `aux_loss`.

## Current State
- `tc_shared` has a local edit for `aux_error` in `src/models/scattermoe_tc.py`.
- `scattermoe_tc` still only supports `aux` and uses the old formula.
- Config validation only allows `none`, `aux`, `deepseek`.
- Docs/config comments do not mention `aux_error`.

## Plan of Action

### 1) Align aux/aux_error formulas in token-choice MLPs
Edit `src/models/scattermoe_tc.py` to support `aux_error` in both classes and
use the scaled-`f` formulation so target is 1.

ScatterMoETokenChoiceMLP (routed experts only):
```python
if self.load_balance_method in ("aux", "aux_error"):
    mask = torch.zeros_like(all_weights)
    mask.scatter_(1, expert_idxs, 1.0 / float(top_k))
    f = mask.mean(dim=0) * n_experts
    if self.load_balance_method == "aux_error":
        f = f - 1.0
    p = all_weights.mean(dim=0)
    metrics["aux_loss"] = torch.sum(f * p)
```

ScatterMoETokenChoiceSharedMLP (routed experts + shared):
```python
if self.load_balance_method in ("aux", "aux_error"):
    mask = torch.zeros_like(all_weights)
    mask.scatter_(1, expert_idxs, 1.0 / float(top_k))
    f = mask.mean(dim=0) * n_routed_experts
    if self.load_balance_method == "aux_error":
        f = f - 1.0
    p = all_weights.mean(dim=0)
    metrics["aux_loss"] = torch.sum(f * p)
```

### 2) Allow aux_error in config validation
Update allowed values in:
- `src/models/model_base.py` (ModelConfig validation and comment)
- `src/config.py` (config validate)

Example changes:
```python
load_balance_method: str = "none"  # "none" | "aux" | "aux_error" | "deepseek"
```
```python
if self.load_balance_method not in ["none", "aux", "aux_error", "deepseek"]:
    raise ValueError(...)
```
```python
assert self.model.get("load_balance_method") in ["none", "aux", "aux_error", "deepseek"]
```

### 3) Update docs/config comments
Files to update:
- `configs/README.md` load_balance_method lists
- `configs/mlp/scattermoe_tc.yaml` comment line
- `configs/mlp/tc_shared.yaml` comment line
- `memory/design/token_choice_moe.md` load balancing methods section:
  - Add `aux_error` description, e.g.
    `aux_error = sum((E * f - 1) * p)` where `f` is mean mask per expert.

### 4) Optional: add aux_error to training script
If desired, update `script/run_tc_shared.sh` to accept `LOAD_BALANCE="aux_error"`
and set:
```bash
LOAD_BALANCE_ARGS="model.load_balance_method=aux_error model.aux_loss_coef=${AUX_LOSS_COEF}"
EXP_NAME="${MLP_TYPE}_aux_error_${AUX_LOSS_COEF}"
```

## Validation
- No tests needed for formula change, but a quick smoke run with
  `load_balance_method=aux_error` should pass config validation and produce
  nonzero `aux_loss` metrics.

## Files to Edit
- `src/models/scattermoe_tc.py`
- `src/models/model_base.py`
- `src/config.py`
- `configs/README.md`
- `configs/mlp/scattermoe_tc.yaml`
- `configs/mlp/tc_shared.yaml`
- `memory/design/token_choice_moe.md`
- (optional) `script/run_tc_shared.sh`
