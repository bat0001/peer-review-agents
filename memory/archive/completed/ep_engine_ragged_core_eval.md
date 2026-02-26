# Plan: Move Eval Shape Handling into Model Base + Batched CORE Eval

## Status

- **Completed:** 2026-02-11
- **Primary outcome:** CORE eval now uses a model-owned generic eval batch path with EP shape alignment handled inside model code.

## Implementation Outcome

- Landed generic model API in `src/models/model_base.py`:
  - `EvalBatchForwardResult`
  - `BaseGPT.forward_eval_batch(...)`
  - `BaseGPT._prepare_ep_eval_inputs(...)`
- CORE eval path in `src/eval/core.py` now:
  - uses model `forward_eval_batch` when available,
  - supports batched prefills via `eval_examples_per_forward`,
  - removed old `_evaluate_task_shape_aligned` and prompt-count bucketing path.
- Eval config now includes:
  - `eval.core_eval_examples_per_forward` (default `1`)
- 2-GPU EP CORE run completed with:
  - checkpoint: `checkpoint_step_100_fixed.pt`
  - command using `CUDA_VISIBLE_DEVICES=2,3` + `torchrun --nproc_per_node=2`
  - result: `CORE = -0.022338`

## Known Gaps / Follow-ups

- EP threshold engine internals (`ParallelExperts.forward_threshold`) were **not** redesigned for true ragged routing in this pass.
  - Current approach keeps collectives aligned by model-side shape alignment for eval calls.
- LOC reduction target was only partially met:
  - `src/eval/core.py` reduced complexity, but model-side helper/API additions increased total LOC overall.
- Existing test drift observed during validation (pre-existing):
  - `test/test_refactored_models.py` config mismatch (`expert_parallel` missing in test config)
  - `test/test_ep_engine.py` unpack arity mismatch vs current engine return signature

## Context

- CORE eval currently carries EP-specific shape/padding/lockstep logic in eval code.
- This makes `eval_core.py` harder to read, harder to maintain, and tightly coupled to one model implementation detail.
- Desired direction: keep the eval entry clean and move distributed shape handling into the model layer.

## Objectives

1. Move padding/shape-alignment logic into `model_base` (or model-side shared utilities owned by model code).
2. Enable batched CORE prefills for speed, with minimal churn to `eval_core.py`.
3. Reduce surface area/files involved in eval-specific distributed shape handling.

## Non-goals

- No major rewrite of CORE task scoring semantics.
- No broad routing-algorithm redesign in this pass.
- No code changes in this step (planning only).

## Target Architecture

### Eval entry stays thin

- `eval_core.py` should mostly:
  - build task batches/microbatches,
  - call one model-facing forward API,
  - score outputs.
- It should not own EP padding internals.

### API boundary decision (tensor vs non-tensor)

- Recommended boundary: eval callers pass **local CUDA tensors** (`input_ids: LongTensor[B_local, T_local]`) to model base.
- Important nuance: "well-shaped" means well-shaped **locally** (valid 2D tensor), not globally equal shape across ranks.
- Model base is responsible for any cross-rank coordination needed by EP internals.
- Avoid passing Python lists/objects into model base as the primary path:
  - Python-object collectives (`all_gather_object`) are slower and less type-safe.
  - It widens the surface for serialization and rank-divergent control flow.
  - It mixes task/rendering concerns with model execution concerns.
- Keep tokenization/rendering and per-example metadata assembly in eval code; keep distributed shape alignment in model code.
- Naming should be generic because this path may be reused by non-CORE evals.

### Deadlock model

- Main deadlock risk is **collective mismatch** (different ranks call different collectives/order), not host-to-device copy itself.
- CPU->GPU copies can add jitter/stragglers but should not deadlock if every rank follows the same model-base collective schedule.
- Therefore model base must enforce:
  - identical collective sequence per eval step across ranks,
  - fixed-order collectives (e.g., max steps/shape exchange before forward),
  - fail-fast assertions when invariants are violated.

### Model base owns shape handling

- Add/standardize a model-side API in `model_base` that:
  - accepts local eval microbatch tensors,
  - performs any required distributed alignment/padding/lockstep internally,
  - runs model forward,
  - returns outputs plus a validity mask/metadata for scoring.
- This keeps EP/non-EP behavior hidden behind a stable inference interface.

### Concrete model-base contract (generic snippet)

```python
# src/models/model_base.py (planned)
from dataclasses import dataclass
from typing import Optional
import torch

@dataclass
class EvalBatchForwardResult:
    losses: torch.Tensor          # (B_exec, T_exec), CE per token, last token NaN
    predictions: torch.Tensor     # (B_exec, T_exec)
    valid_rows: torch.Tensor      # (B_exec,), bool; True for real rows, False for internal dummies
    local_row_ids: Optional[torch.Tensor] = None  # Optional mapping back to caller's microbatch rows

class BaseGPT(nn.Module):
    ...
    @torch.no_grad()
    def forward_eval_batch(self, input_ids: torch.Tensor) -> EvalBatchForwardResult:
        """
        input_ids: local tensor (B_local, T_local), already on device.
        Generic eval-prefill API (CORE and other evals).
        Handles EP/non-EP dispatch internally.
        """
        if self._is_ep_distributed():
            input_exec, valid_rows = self._prepare_ep_eval_inputs(input_ids)
        else:
            input_exec = input_ids
            valid_rows = torch.ones(input_ids.size(0), dtype=torch.bool, device=input_ids.device)

        outputs = self(input_exec)  # Existing forward path
        logits = outputs.logits

        target_ids = torch.roll(input_exec, shifts=-1, dims=1)
        losses = torch.nn.functional.cross_entropy(
            logits.view(-1, logits.size(-1)),
            target_ids.view(-1),
            reduction="none",
        ).view_as(input_exec)
        losses[:, -1] = float("nan")
        predictions = logits.argmax(dim=-1)
        return EvalBatchForwardResult(losses=losses, predictions=predictions, valid_rows=valid_rows)
```

### EP preparation internals in model base (snippet)

```python
# src/models/model_base.py (planned internal helper)
@torch.no_grad()
def _prepare_ep_eval_inputs(self, input_ids: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Guarantee rank-aligned collective participation for EP eval.
    Does NOT require equal B_local/T_local on entry.
    """
    import torch.distributed as dist

    assert dist.is_initialized()
    device = input_ids.device
    pad_id = 0  # BOS or configured pad id; finalized during implementation

    # 1) Every rank announces whether it has real work this step.
    has_work = torch.tensor([1 if input_ids.numel() > 0 else 0], device=device, dtype=torch.long)
    dist.all_reduce(has_work, op=dist.ReduceOp.SUM)

    # 2) Exchange seq length requirement for this step.
    t_local = torch.tensor([input_ids.size(1) if input_ids.numel() > 0 else 1], device=device, dtype=torch.long)
    dist.all_reduce(t_local, op=dist.ReduceOp.MAX)
    t_exec = int(t_local.item())

    # 3) Ensure each rank has at least one row to keep call graph aligned.
    if input_ids.numel() == 0:
        input_exec = torch.full((1, t_exec), pad_id, device=device, dtype=torch.long)
        valid_rows = torch.zeros(1, device=device, dtype=torch.bool)
        return input_exec, valid_rows

    # 4) Pad local seq dim only to step max (not full-task global max).
    if input_ids.size(1) < t_exec:
        padded = torch.full((input_ids.size(0), t_exec), pad_id, device=device, dtype=input_ids.dtype)
        padded[:, :input_ids.size(1)] = input_ids
        input_ids = padded

    valid_rows = torch.ones(input_ids.size(0), device=device, dtype=torch.bool)
    return input_ids, valid_rows
```

### Eval-core call site after migration (snippet)

```python
# src/eval/core.py (planned)
result = model.forward_eval_batch(input_ids)
losses = result.losses
predictions = result.predictions
valid_rows = result.valid_rows

if valid_rows.any():
    # scoring unchanged; index only valid rows if dummies were injected internally
    ...
```

### Batched CORE eval

- CORE switches from per-example prefills to microbatched prefills.
- Grouping policy remains simple and explicit (e.g. by task/prompt structure), while all distributed shape mechanics stay inside model code.
- The batch dimension increase should be the main speedup lever.

## Proposed Work Plan

### Phase 1: Define model-base eval-forward contract

- Introduce a single eval-forward path in model base for generic eval usage (CORE first adopter).
- Contract includes:
  - input tensors and optional microbatch metadata,
  - returned logits/loss-relevant outputs,
  - returned mask/indices indicating real vs. internal dummy/padded rows.
- Keep fail-fast behavior for unsupported modes.
- Explicitly codify local-vs-global shape invariants:
  - caller provides valid 2D local tensor only,
  - model base handles cross-rank coordination,
  - eval never calls `dist.*` for shape alignment anymore.

### Phase 2: Relocate padding/lockstep logic into model code

- Move current eval-side EP shape handling into model-owned implementation.
- Prefer consolidation over new helper sprawl:
  - either keep logic directly in `model_base`,
  - or in one tightly-scoped model-side helper module used by `model_base`.
- Remove duplicated eval-side shape logic once model path is validated.
- Keep helper count minimal: one model-base entry + at most one internal helper.

### Phase 3: Batched CORE integration with minimal eval diff

- Update CORE loop to form microbatches and call the new model-base eval-forward.
- Keep scoring code largely unchanged by using returned validity metadata.
- Ensure distributed call counts remain aligned via model-side handling.

### Phase 4: Validation

- Correctness:
  - compare batched vs. existing per-example CORE results on small subsets.
  - verify rank-consistent completion (no collective mismatch/hang).
- Performance:
  - measure tokens/s or examples/s before vs. after on representative CORE tasks.
- Regression checks:
  - confirm non-CORE inference paths are unaffected.

## File-Level Change Intent (for implementation step)

- Primary:
  - `src/models/model_base.py` (or equivalent model-base file): new canonical eval-forward path + internal shape handling.
  - `src/eval/core.py`: reduced to clean batching/scoring entry usage.
- Secondary (only if necessary):
  - one model-side helper file for internal distributed shape utilities.
- Avoid proliferating new eval-specific files.

## LOC Reduction Constraints

- Net LOC target: neutral or negative across `src/eval/core.py` + `src/models/model_base.py` for this refactor stage.
- Delete/replace, do not wrap:
  - remove `_evaluate_task_shape_aligned` from eval once model-base path is validated.
  - avoid keeping dual long-lived code paths with duplicated logic.
- Keep public API minimal:
  - one model entry (`forward_eval_batch`),
  - one optional internal helper (`_prepare_ep_eval_inputs`),
  - no extra abstraction layer unless it removes more lines than it adds.
- Prefer reusing existing forward/loss code blocks instead of introducing parallel implementations.

## Risks and Mitigations

- Risk: model-base API grows unclear.
  - Mitigation: keep one explicit generic eval-forward contract and document tensor shapes.
- Risk: confusion about tensor boundary ("must be globally equal shape").
  - Mitigation: document that only local tensor shape is required; global alignment is model-owned.
- Risk: hidden padding/masking bugs affect scoring.
  - Mitigation: strict validity-mask contract and batched-vs-baseline parity tests.
- Risk: rank hangs from divergent control flow.
  - Mitigation: enforce identical collective order in model-base helper; add assertion checks and EP 2-GPU smoke tests.
- Risk: too much refactor at once.
  - Mitigation: phase rollout, keep `eval_core.py` diff small, and delete old path only after parity.

## Rollout Sequence

1. Land model-base eval-forward contract.
2. Move padding/lockstep internals from eval into model code.
3. Switch CORE to microbatched forward calls through the new contract.
4. Run parity + performance checks, then remove deprecated eval-side shape logic.
