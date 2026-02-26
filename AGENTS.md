# Repository Guidelines

## Machine-Specific Configuration

Always check `MACHINE.md` for server-specific paths, conda environments, and data locations.

Available machine configs:
- `MACHINE.md` - A5000 server (local)
- `MACHINE_b200.md` - B200 server (HiPerGator, remote)

**Required environment variable**: `NANOCHAT_BASE_DIR` must be set (code will fail fast if not).

Before you run any code, always check `MACHINE.md` to see if the machine you are using is supported!!!

## Project Structure & Module Organization
`src/` captures shared infrastructure (training loops, configuration plumbing, dataset streaming). `src/models/` contains architecture implementations; `src/models/gec.py` is the canonical Global Expert Choice (GEC) MLP. `megablock/` vendors MegaBlocks’ Triton/CUDA kernels. `benchmark/` hosts instrumentation: `benchmark/mlp/` benchmarks dense vs. GEC layers, while `benchmark/permutation/` isolates gather/scatter performance. Tests mirror the package layout under `test/`; experiment assets reside in `configs/`, `yamls/`, and `data/`.

## GEC/EC Architecture

This codebase implements Expert Choice (EC) and Global Expert Choice (GEC) MoE routing, as described in the paper (`memory/paper_draft/example_paper.tex`). **In code, both live under the "GEC" name** — EC corresponds to `topk` routing mode and GEC corresponds to `threshold` routing mode.

### Two Routing Modes

- **`topk` mode (= EC in the paper)**: Each expert selects exactly k tokens via top-k on router logits. Perfect load balance. Non-causal (needs full batch). Default for training.
- **`threshold` mode (= GEC in the paper)**: Each token independently checks `router_logit(t,i) > cutoff_ema[i]`. Causal. Always used at eval/inference, optionally at training with warmup.

The `ExpertEngine` (in `src/models/engines/engine.py`) tracks an EMA of the top-k cutoff per expert. This EMA is the bridge: trained under `topk`, it enables causal `threshold` routing at inference.

### Model Types

| Config (`mlp=`) | Class | Description |
|---|---|---|
| `gec` | `GECMLP` | Routed experts only |
| `gec_shared` | `GECSharedMLP` | Routed + shared expert (primary config) |
| `ec_shared` | `ECSharedMLP` | GEC_shared + chunked routing (`routing_chunk_seqs`) |
| `tc` / `tc_shared` | `ScatterMoETokenChoice*MLP` | Token-choice baseline (ScatterMoE Triton kernels) |

`GECSharedMLP` is the main model. `ECSharedMLP` inherits from it, only overriding `forward_topk()` to add per-sequence/chunk routing. Shared expert is always active for every token.

### Architecture

```
GEC / GEC_shared (thin wrappers: normalization + scatter)
    ↓ composes
ExpertEngine (router → topk/threshold selection → batched expert BMM → cutoff EMA)
    ↓ returns unweighted outputs
Scatter Backend (fused weighted aggregation: routed + shared in one pass)
```

Four scatter backends: `index_add` (default), `index_add_fp32`, `csr`, `csr_optimized`. Switch via `model.scatter_backend` in config.

### Key Details

- **Eval always uses threshold routing** regardless of training mode (`gec_shared.py:109`).
- **Capacity constraints** can bound expert usage during threshold training: `expert_capacity_factor`. See `memory/design/capacity_constraints.md`.
- **Warmup**: First N steps use `topk` before switching to `threshold` training (`threshold_warmup_steps`).
- **Token-choice baseline** (`tc_shared`): Tokens select top-k experts. Uses ScatterMoE Triton kernels. Supports aux-loss and DeepSeek-style load balancing.

For notation (G, E, k formulas), see `memory/design/notation.md`. For full implementation details, see `src/models/README.md`.

## Operational & Workflow Practices
- Always check GPU availability (`nvidia-smi`) (to see if current GPU memory usage is near zero) before launching any training, benchmarking, or test command.
- Favor the best architecture rather than backward compatibility; refactor when it materially improves clarity or performance.
- After any API change, search for every call site, enumerate them, and confirm with the user before updating.
- When debugging or experimenting, run with `+experiment=debug`; surface implementation plans for approval before making speculative fixes.
- Let exceptions propagate (fail fast) everywhere except `utils/`, which may handle ingestion errors.
- Hydra is required for config composition (`python train.py model_size=tiny mlp=gec_shared +experiment=debug`); scripts belong under `script/`.
- Model-module validation often runs through `benchmark/` (benchmarking counts as testing). Other integration/unit tests live in `test/`, and `test/test_weight_init.py` must run after any initialization change (see `memory/testing/`).
- Weight decay defaults to `0.0` for nanochat-style training—Muon supplies enough implicit regularization.
- Before modifying initialization, routing, or kernels, consider whether a broader refactor keeps the system maintainable and mention both the tactical and refactor options to the user.

## Memory Management

Whenever you need to update memory, skim this file for quick reminders and follow the full protocol in `memory/README.md`.

### Three-Tier System

**AGENTS.md (Agent Core Memory)**
- Stable, fundamental knowledge ALL future agents need
- Notation, conventions, core implementation principles
- Must remain concise; updated rarely
- Location: `/AGENTS.md`

**memory/ (Agent Working Memory)**
- Detailed design docs, implementation plans, benchmarks
- Evolves frequently during active development
- Can be verbose and detailed
- Location: `/memory/` (see memory/README.md for index)

**Module READMEs (Module-Specific Docs)**
- Architecture and API of a single module
- Usage examples and setup instructions
- Read by both agents and humans
- Location: Scattered (e.g., `src/models/README.md`, `benchmark/README.md`)

### What Goes Where?

| Information Type | Location | Why |
|-----------------|----------|-----|
| High-level: What is GEC? | AGENTS.md | Core conceptual knowledge |
| Detailed notation (G, E, k formulas) | `memory/design/notation.md` | Cross-cutting notation system |
| Routing implementation details | `src/models/README.md` | Module-specific architecture |
| Normalization design rationale | `memory/design/` | Cross-module design decision |
| Benchmark results | `memory/benchmarks/` | Working analysis |
| "How to run benchmarks" | `benchmark/README.md` | Module-specific usage |
| Bug reports and debug logs | `memory/bugs/` | Issue tracking and fixes |
| Refactoring plans | `memory/plans/` | Active cross-module work |
| Triton kernel API | `src/kernels/README.md` | Module-specific API |

### Update Protocol

**Agent behavior (see `memory/README.md` for details):**
- Explicit requests → Execute directly
- Implied documentation → Present plan with content preview
- Agent discoveries → Present plan with justification

**CLAUDE.md** - Highest content bar:
- Only for knowledge ALL future agents must know
- Stable conventions and permanent principles
- Must be concise and fundamental

**memory/** - Working knowledge:
- Cross-module designs and rationale
- Benchmarks and performance analysis
- Implementation plans (extract design decisions before archiving)
- See `memory/README.md` for detailed guidelines

**Module READMEs** - Module-specific:
- Architecture and APIs of that module
- Usage examples and setup instructions
- Can edit more freely when updating that module

**Archive protocol:**
- Extract design decisions from plans → `memory/design/`
- Completed plans → `memory/archive/completed/`
- Superseded designs → `memory/archive/deprecated/`
- Old benchmarks → `memory/archive/old_benchmarks/`

---

## Triton Kernel Notes
See `src/kernels/README.md` for current gather/scatter assumptions, fused-kernel coverage, and validation steps. Record performance deltas in `memory/benchmarks/speedup.md` after kernel changes.

## Reference Repositories
Several read-only sibling repos supply inspiration but should never be modified directly: `scattermoe/` (Triton SMoE kernels), `megablock/` (vendored MegaBlocks kernels), `nanochat/` (minimal end-to-end LLM training stack), and `moe_plus_plus/` (MoE++ with zero-computation experts).

**NOTE: DON'T EVER EDIT THESE REPOSITORIES.**

## Build, Test, and Development Commands
```bash
pip install -e .[dev]                        # editable install with lint/dev extras
python benchmark/mlp/benchmark.py --help     # dense vs. GEC benchmarking
python benchmark/permutation/suite.py        # gather/scatter microbenchmark (CUDA)
python train.py --config yamls/gec.yaml      # example training invocation
```

## Coding Style & Naming Conventions
PEP 8 conventions, 4-space indentation, descriptive docstrings, and type hints are expected. Modules/functions use `snake_case`; classes use `PascalCase`; constants are uppercase. Run `black`, `ruff`, and optional type checks before committing. Comment Triton kernels to explain index math and memory layouts.

## Testing Guidelines
Test structure mirrors source modules (`test/models/test_gec.py`, etc.). Name tests after behaviors (`test_router_respects_capacity`). Cover routing extremes (duplicate selections, zero-coverage tokens) and validate Triton vs. torch parity. Benchmark kernels after changes and attach metrics to PRs. 

Don't use pytest.

## Commit & Pull Request Guidelines
Compose concise, imperative commit summaries (`feat: add balanced gather kernel`) with bodies explaining rationale, tests, and benchmarks. Reference issues (`Refs #123`). PRs should describe motivation, enumerate validation (tests + benchmark outputs), and update documentation (`AGENTS.md`, `speedup.md`, this guide) when assumptions shift.