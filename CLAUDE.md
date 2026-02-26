# Claude Memory

## Machine-Specific Configuration

Always check `MACHINE.md` for server-specific paths, conda environments, and data locations.

Available machine configs:
- `MACHINE.md` - A5000 server 
- `MACHINE_b200.md` - B200 server (HiPerGator) (current)

**Required environment variable**: `NANOCHAT_BASE_DIR` must be set (code will fail fast if not).

## What is GEC/EC?

This codebase implements Expert Choice (EC) and Global Expert Choice (GEC) MoE routing, as described in the paper (`memory/paper_draft/example_paper.tex`). **In code, both are under the "GEC" name** — EC corresponds to `topk` routing mode and GEC corresponds to `threshold` routing mode.

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

## Project Guidelines

- **No backward compatibility** – Do not worry about backward compatibility; keep the code concise. Always consider the best and most effective way to implement something, and refactor whenever it is beneficial.
- **After API Changes** - If you change a function or class API, search the codebase for all usages, list them, and ask whether you should update those call sites as well.
- **Consider refactoring** - If you are doing some major change to the logic, instead of only adding new code locally, consider refactoring the larger system to make it more maintainable. Report both solutions to the user and let them decide.
- **Testing** - Model module testing uses `benchmark/` (benchmarking is testing); all other testing files go in `test/`. **Critical:** Run `test/test_weight_init.py` after any changes to initialization (see `memory/testing/`)
- **Check GPU first** - Before testing or running the code, ALWAYS ALWAYS ALWAYS check GPU availability using the nvidia-smi command (add your favorite flags etc.)
- **Debugging** - When debugging, use `+experiment=debug` (disables compilation, wandb, and visualization for faster iteration)
- **Debugging** - When debugging and testing, do not be too eager to change the code even if a test succeeds. Instead, present user an implementation plan and ask them for approval before proceeding.
- **Let it crash** - In almost all cases, do not catch or handle errors; let exceptions propagate and fail fast. This helps us find bugs quickly and notice when behavior is unexpected. The only exception is in `utils/`, which may handle errors during data preparation.
- **Configuration** - Use Hydra for all config management. Compose configs from groups: `python train.py model_size=tiny mlp=gec_shared +experiment=debug`. See `configs/README.md` for details.
- **Scripts** - Put bash/slurm scripts in `script/`. Python entrypoints (Hydra CLIs) go at repo root next to `train.py`.
- **Read the code** - Explore agents use Haiku, a small model with limited reasoning. Always verify its findings by reading the key code yourself rather than trusting its results blindly.

Again: **ALWAYS READ THE CODE AFTER USING EXPLORE AGENTS!!!**

## Plan Mode

- If user is not sure about a choice, you should present a detailed plan of every choice and let them decide. Once they decided on one option, redo the plan entirely, remove the other options, and present the new plan.

## Memory Management

Whenever user asks you to do anything with memory, you should first check the CLAUDE.md and memory/README.md to understand how memory is organized.

### Three-Tier System

**CLAUDE.md (Agent Core Memory)**
- Stable, fundamental knowledge ALL future agents need
- Notation, conventions, core implementation principles
- Must remain concise; updated rarely
- Location: `/CLAUDE.md`

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
| High-level: What is GEC? | CLAUDE.md | Core conceptual knowledge |
| Detailed notation (G, E, k formulas) | `memory/design/notation.md` | Cross-cutting notation system |
| Routing implementation details | `src/models/README.md` | Module-specific architecture |
| Normalization design rationale | `memory/design/` | Cross-module design decision |
| Weight initialization design | `memory/design/initialization.md` | Cross-module design decision |
| Benchmark results | `memory/benchmarks/` | Working analysis |
| "How to run benchmarks" | `benchmark/README.md` | Module-specific usage |
| Model performance tests | `benchmark/` | Testing via benchmarking |
| Integration/system tests | `test/` | Non-model testing |
| Critical test documentation | `memory/testing/` | Test rationale and bug history |
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


## Reference Repositories

We have several reference repositories locally that you can use to get ideas or code snippets. However, you should never edit these repositories directly. The repos include: 

- `scattermoe/`: Triton-based implementation of Sparse Mixture-of-Experts (SMoE) on GPUs.
- `megablock/`: MegaBlocks' Triton/CUDA kernels.
- `nanochat/`: Nanochat's training code (Oct 2025 snapshot). Developed by Andrej Karpathy for training small-scale ChatGPT-like models end-to-end. Designed for budgets of ~$100-$1000 on a single 8XH100 node.
- `nanochat_updated/`: Nanochat (Jan 2026). Key changes: rustbpe now pip package, GQA via PyTorch `enable_gqa`, synthetic identity data, approximate training resume, CustomJSON task.
- `nanochat_260111/`: Latest nanochat (Jan 11, 2026). Key changes: Flash Attention 3, sliding window attention (SSSL), learnable lambdas (resid/x0), Polar Express + NorMuon variance reduction in Muon, cautious weight decay, gradient clipping removed. See `memory/reference/nanochat_changelog.md`.
- `moe_plus_plus/`: MoE++'s implementation of Sparse Mixture-of-Experts (SMoE) on GPUs, where we have zero-computation experts like noop or bias experts.

**NOTE: DON'T EVER EDIT THESE REPOSITORIES.**