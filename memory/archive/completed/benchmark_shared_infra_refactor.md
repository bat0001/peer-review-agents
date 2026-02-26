# Benchmark Shared Benchmark Infrastructure Refactor

**Status:** Option A implemented (shared package + shims). Follow-ups: decide on harness unification and shim removal timeline.

## Context
- `benchmark/mlp` currently imports `BenchmarkConfig`, `TorchCompileManager`, `add_standard_args`, `args_to_config`, `get_tolerance`, and `setup_environment` from `benchmark/permutation/core.py` (see `benchmark/mlp/core.py`) and reuses `BenchmarkResult`, `measure`, and `_render_table` from `benchmark/permutation/common.py` (see `benchmark/mlp/common.py` and `benchmark/mlp/base.py`).
- `benchmark/permutation/core.py` is titled “Configuration for permutation benchmarks” but now carries MLP-only flags (`routing_mode`, `gec_config`) and help strings into the permutation CLI. Those flags are unused in permutation benchmarks yet appear in `python -m benchmark.permutation` help output.
- We now have two similar harnesses (`benchmark/permutation/base.py` and `benchmark/mlp/base.py`) with parallel timing/validation code that drift independently even though they rely on the same `measure`/`BenchmarkResult` primitives.
- The top-level `benchmark/README.md` still reflects the older `benchmark/mlp/gec*` layout and does not mention the new permutation/MLP coupling, so readers cannot tell which utilities are safe to depend on.

## Goals
- Isolate truly shared benchmark utilities (config parsing, timing, result formatting, torch.compile wrappers, environment setup) into a neutral location so MLP does not depend on permutation internals.
- Give permutation benchmarks a clean CLI without routing-only flags, and keep MLP routing flags scoped to the MLP entrypoints.
- Reduce harness drift by centralizing the common timing/validation scaffolding while still letting MLP keep its two-stage validation specifics.
- Preserve backward compatibility for existing import paths long enough to migrate downstream scripts (thin re-exports or deprecation shims).

## Proposed Refactor (two viable implementations)

### Option A — New `benchmark/shared/` package (preferred)
- Create `benchmark/shared/config.py` with a neutral `BenchmarkConfig` (tokens, hidden, granularity, expansion, repeats, warmup, device) plus optional mixins or helper builders for routing-specific flags (e.g., `add_routing_args` returning `routing_mode`/`gec_config` only when requested).
- Move `TorchCompileManager` to `benchmark/shared/compile.py`.
- Move `BenchmarkResult`, `measure`, and `_render_table` to `benchmark/shared/results.py` (or `formatting.py`), keeping dataclass fields stable.
- Move `setup_environment` (sys.path, TRITON env, CUDA check) to `benchmark/shared/env.py`.
- Update imports:
  - `benchmark/permutation/*` use the shared modules; `add_standard_args` in permutation becomes kernel-only (drops routing flags).
  - `benchmark/mlp/*` import from `benchmark/shared/*` and call a routing-specific arg helper when building their parser.
- Leave `benchmark/permutation/core.py` and `benchmark/permutation/common.py` as thin re-export shims (with a `TODO`/deprecation note) to avoid immediate breakage for downstream users.
- Update `benchmark/README.md` and `benchmark/permutation/README.md` to document the new layering and CLI flag split.

### Option B — Shared base harness class without directory split
- Keep files under `benchmark/permutation/`, but introduce `benchmark/permutation/shared.py` that holds the neutral config/result/timing pieces.
- Rewrite both `benchmark/permutation/base.py` and `benchmark/mlp/base.py` to subclass a single `BaseBenchmark` with hooks:
  - `setup_data()`
  - `create_implementations()`
  - `compute_bytes()`
  - Optional `validate(outputs, reference_outputs)` override so MLP can keep its two-stage validation.
- Drop routing flags from `add_standard_args`; provide a separate `add_routing_args` used only by `benchmark/mlp`.
- This avoids a new directory, but still decouples the routing-only CLI bits and reduces duplication.

## Implementation Steps (assuming Option A; Option B mirrors file moves inside permutation/)
1) Draft shared modules: `benchmark/shared/{config.py,compile.py,results.py,env.py}` with existing code moved verbatim to keep behavior identical. Add a small `add_routing_args(parser)` helper that only MLP calls.
2) Update permutation benchmarks:
   - Import shared modules, slim `add_standard_args` to kernel-only flags.
   - Keep `core.py`/`common.py` as re-export shims that warn or comment about migration.
3) Update MLP benchmarks:
   - Point imports to `benchmark/shared/*`.
   - Compose CLI as `add_standard_args` + `add_routing_args`.
   - If desired, subclass a shared `BaseBenchmark` class (moved to `benchmark/shared/harness.py`) and keep MLP’s grouping/diagnostics by overriding a `validate_groups()` hook.
4) Documentation and samples:
   - Refresh `benchmark/README.md` structure diagram and flag descriptions.
   - Add a short note in `benchmark/mlp/README.md` that routing flags live only on the MLP CLI.
   - If keeping shims, annotate them with removal timeline.
5) Validation pass:
   - Dry-run CLI help to ensure permutation benchmarks no longer expose routing flags.
   - Spot-check `python -m benchmark.permutation scatter-forward --repeats 2 --warmup 1` and `python -m benchmark.mlp forward --repeats 2 --warmup 1 --routing-mode topk` (after `nvidia-smi`) to confirm wiring.
   - Run `python -m benchmark.mlp` once with `--routing-mode threshold` to ensure routing args still parse.

## Open Questions / Decisions
- Naming: prefer `benchmark/shared/` vs `benchmark/common/`? (Defaulting to `shared` unless we want to reserve `common` for data assets.)
- Should `BenchmarkConfig` stay G/E-specific or become pluggable (e.g., allow overriding `num_experts` derivation for non-GEC experiments)?
- Do we keep legacy import shims permanently, or schedule removal after a release?
- Should we unify the validation paths (`BaseBenchmark.run_single_case`) so MLP uses the same measurement loop with a hook for grouped validation, or leave two separate loops for clarity?
