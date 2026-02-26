# Agent Working Memory

## Purpose

This directory contains detailed design documents, implementation plans, and benchmarks that agents use as working memory across sessions.

**For stable core knowledge**, see `/CLAUDE.md`.
**For module-specific information**, see module READMEs (e.g., `src/models/README.md`).

## Directory Structure

### design/
Design documents and architectural decisions affecting multiple modules.

- **`notation.md`** - MoE/GEC notation system (G, E, k formulas, unified notation, validation rules)
- **`gate_activation_normalization.md`** - Router activation functions (sigmoid/relu/softmax) and normalization strategies (fanout/select_norm/all_norm)
- **`logging_architecture.md`** - Hierarchical wandb logging structure and design decisions (no model prefixes, flat vs hierarchical)
- **`metric_logging_deadlock_prevention.md`** - Metric pipeline architecture preventing distributed deadlocks (three-zone model, conversion boundary, API enforcement, 2025-11-10)
- **`initialization.md`** - Property-based weight initialization design (aspect-ratio scaled Kaiming, nanochat pattern, expert weight handling)
- **`token_choice_moe.md`** - Token-choice MoE design (scattermoe_tc): routing comparison with GEC, load balancing methods, parameter layout
- **`checkpointing.md`** - Checkpoint invariants (EP expert index contiguity, repair path)
- **`capacity_constraints.md`** - Expert capacity constraints for threshold routing (bounding expert usage within +/- alpha of target k)
- **`cutoff_accumulation.md`** - Step-boundary pattern for freezing cutoff EMAs across micro-batches, DDP synchronization
- **`dtype_handling.md`** - Mixed precision dtype handling in GEC models (FP32 promotion fix, accumulation precision)
- **`ec_shared.md`** - ECSharedMLP chunked expert-choice routing with shared expert
- **`flat_api.md`** - Flat API design for ExpertEngine/ParallelExperts (flat tensors instead of padded batched)
- **`prealloc_all_to_all.md`** - PreallocAllToAllOp zero-copy expert dispatch for Expert Parallelism
- **`sequential_add_strategy.md`** - Sequential Add Triton kernel for bandwidth-optimal MoE output recombination
- **`threshold_routing_design.md`** - Threshold routing design (for-loop rationale, dual-mode training, two-gate schedule: `ema_start_steps` + `threshold_warmup_steps`, DDP cutoff sync)
- **`eval_batch_forward_interface.md`** - Generic eval prefill interface (`forward_eval_batch`) and model-owned EP shape alignment contract

### testing/
Critical tests and testing documentation.

- **`README.md`** - Testing philosophy and critical test overview
- **`weight_initialization.md`** - Weight init bug discovery, fix, and comprehensive test documentation

### bugs/
Bug reports and debugging logs documenting issues, root causes, and fixes.

- **`deadlock_item_calls.md`** - Multi-GPU deadlock from .item() calls: three incidents documented with final architectural fix via metric pipeline refactoring (RESOLVED, 2025-11-10; kept for prevention guidelines)
- **`ep_checkpoint_index_gaps.md`** - EP checkpoint expert indices saved with gaps; fix script + save fix (RESOLVED, 2026-01; kept while affected runs may still exist)
- **`cutoff_ema_updates_checkpoint_compat.md`** - Eval checkpoint compatibility: older checkpoints may have `cutoff_ema` without `cutoff_ema_updates`; loader allows only that missing-key pattern
- **`core_eval_fewshot_small_subset.md`** - CORE eval failure on tiny subsets when few-shot sample size exceeds available population (OPEN, 2026-02)
- **`test_script_drift_eval_refactor.md`** - Test-script drift notes discovered during eval refactor validation (OPEN, 2026-02)
- **`TODO.md`** - Open investigation: aux loss uses softmax while gate uses `apply_router_activation`

**Bug documentation typically includes:**
- Summary, symptoms, and root cause
- The fix and code changes
- Prevention guidelines when applicable
- Testing verification steps

### benchmarks/
Performance analysis and optimization plans.

- **`core_eval_batched_prefill_2026_02.md`** - 2-GPU CORE eval validation for batched prefills + model-owned eval batch path (2026-02)

### plans/
Active implementation plans spanning multiple modules. Archive when completed.

- **`refactor_simplify_norm_scatter_keep_metrics.md`** - Refactoring plan for normalization/scatter/metrics simplification
- **`routing_stability_gec_tc_ec.md`** - Cross-family routing stability analysis plan (GEC vs EC vs TC) with checkpoint-pair metrics and visualization suite

**Recently archived (2026-02):**
- `eval_moe_visualization.md` → completed, generalized MoE eval visualization (includes B200 remote update notes)
- `loss_vs_expert_usage_failure_modes.md` → archived from plans (superseded by token-level eval visualization path)
- `ep_engine_ragged_core_eval.md` → completed, archived
- `fix_ec_shared_chunked_routing.md` → completed, archived
- `fix_gec_shared_eval_dtype.md` → completed, archived
- `moe_init_scaling.md` → deprecated (superseded by unified aspect-ratio Kaiming init)
- `domain_specific_routing.md` → deprecated (future work, not actively pursued)

### reference/
Documentation about reference repositories (nanochat, scattermoe, etc).

- **`nanochat_changelog.md`** - Differences between old nanochat (Oct 2025) and nanochat_updated (Jan 2026)

### archive/
Completed plans, superseded designs, and historical benchmark results. 54 completed, 18 deprecated, 2 debugging, 1 old benchmark.

- `archive/completed/` - Finished implementation plans and resolved bugs (54 files). Key entries:
  - `eval_moe_visualization.md` - Unified token-level MoE eval visualization (`loss vs fanout`, `fanout vs position`, correlations), script rename + B200 remote update note (2026-02)
  - `loss_vs_expert_usage_failure_modes.md` - Archived offline-analysis plan, superseded by token-level eval instrumentation path (2026-02)
  - `ep_engine_ragged_core_eval.md` - Model-owned eval batch path + CORE batched prefill plan, completed with validation notes (2026-02)
  - `fix_ec_shared_chunked_routing.md` - ECSharedMLP chunked routing + CLI flag (2026-02)
  - `fix_gec_shared_eval_dtype.md` - Dtype mismatch fix in eval (2026-02)
  - `expert_specialization_analysis.md` - Expert specialization analysis (2026-01)
  - `threshold_warmup_eval_topk.md` - Eval used top-k during warmup fix (2026-01, from bugs/)
  - `torch_compile_recompilation.md` - torch.compile recompilation from dynamic list (2025-12, from bugs/)
  - `cutoff_accumulation_bug2.md` - DDP cutoff divergence fix (2025-11, from bugs/)
  - `aux_loss_logging.md` - Aux loss inflating train loss fix (2025-01, from bugs/)
  - `visualization_empty_fix.md` - Empty viz directory fix (2025-10, from bugs/)
  - `threshold_training_debug_log.md` - Threshold training debug journal (2025-10, from bugs/)
  - `scatter_backend_refactoring.md` - Engine refactor: unweighted returns + scatter backends (2025-12)
  - `expert_parallel_train_integration.md` - EP training init (2025-12)
  - *(and 43 more — see directory listing)*
- `archive/deprecated/` - Superseded design documents and implementation notes (18 files). Key entries:
  - `engine_architecture.md` - Outdated ExpertEngine architecture doc (2026-02, superseded by code evolution)
  - `router_metrics.md` - Outdated router metrics reference (2026-02, code diverged significantly)
  - `visualization_strategy.md` - Outdated visualization design (2026-02, EvalVisualizer is dead code)
  - `domain_specific_routing.md` - Future work routing analysis (not actively pursued)
  - `moe_init_scaling.md` - Earlier MoE init scaling (superseded by unified aspect-ratio Kaiming)
  - `gec_variants/` - Archived GEC source code before ExpertEngine refactor
  - *(and 12 more — see directory listing)*
- `archive/debugging/` - Archived debugging timelines and false diagnoses
  - `cutoff_ema_sync_false_diagnosis.md` - False diagnosis (2025-11-07 to 2025-11-10)
  - `deadlock_item_calls_full_history.md` - Full deadlock debugging history
- `archive/old_benchmarks/` - Historical performance results
  - `speedup.md` - GEC MLP benchmarks on A5000 (Sep 2025, code references outdated)

## Agent Documentation Protocol

### How agents should behave (applies to all locations)

#### Situation 1: User gives clear direction
**Examples:**
- "Add this to memory/design/"
- "Update the benchmark results"
- "Document this in CLAUDE.md"
- Working from existing plans in memory/plans/

**Agent behavior:** Execute directly

#### Situation 2: User implies documentation
**Examples:**
- "Remember that routing uses fanout normalization"
- "Keep in mind the GEC formula is..."
- "Note that we decided to use sigmoid instead of softmax"

**Agent behavior:** Present plan with content preview
```
"I'll document this in memory/design/gate_activation_normalization.md:
- Add section on fanout normalization choice
- Content: [actual content you'll write]
Should I proceed?"
```

#### Situation 3: Agent discovers something worth documenting
**Examples:**
- Found important design pattern while coding
- Completed benchmark with interesting results
- Realized a convention is being used consistently

**Agent behavior:** Present plan with justification
```
"I found that GEC achieves 0.68x dense speed. I can update memory/benchmarks/speedup.md with:
- Current performance metrics
- Identified bottlenecks
- Proposed optimizations
Should I make this update?"
```

## Content Criteria (what belongs where)

**Note:** These are content standards, not permission levels. The behavioral protocol above applies regardless of destination.

### CLAUDE.md (Highest content bar)

**Only add when:**
- Information must be known by ALL future agents
- Convention or principle is stable and permanent
- Content is concise and fundamental
- Examples: Python paths, core project guidelines, memory system structure

**Not for:**
- Detailed explanations (use memory/)
- Module-specific info (use module READMEs)
- Temporary decisions or explorations

### memory/ (Working knowledge)

**Add design/ document when:**
- After finishing design features that affect multiple modules
- After making architectural decisions with project-wide implications
- Documenting design rationale for future agents

**Add benchmarks/ document when:**
- Recording performance analysis results
- Documenting optimization plans and speedup results

**Add plans/ document when:**
- Planning refactoring spanning multiple modules
- Designing complex features requiring multiple steps
- Brainstorming design decisions
- Coordinating changes across codebase

### Module READMEs (Module-specific)

**Use module README (e.g., `src/models/README.md`) when:**
- Documenting architecture of a single module
- Explaining module-specific APIs
- Providing usage examples for the module
- Describing module file organization

**Can edit more freely when:**
- Making code changes to that module
- Updating API documentation after refactoring
- Adding usage examples for new features

## Examples

| Information | Correct Location | Reason |
|-------------|------------------|--------|
| "High-level: What is GEC?" | CLAUDE.md | Core conceptual knowledge |
| "Detailed: G, E, k formulas and validation rules" | memory/design/notation.md | Cross-cutting notation system |
| "Why we chose fanout over select_norm normalization" | memory/design/ | Design rationale, may evolve |
| "GECMLP class API and forward pass logic" | src/models/README.md | Module-specific architecture |
| "Benchmark shows 0.68x dense speed, plan to optimize" | memory/benchmarks/ | Active performance work |
| "How to run MLP benchmarks with custom configs" | benchmark/README.md | Module-specific usage |
| "Multi-GPU deadlock from .item() calls" | memory/bugs/ | Bug with prevention insights |
| "Plan to refactor benchmark base classes" | memory/plans/ | Active cross-module work |

## Maintenance

### Archive Protocol

**When you complete a plan:**
- Identify design decisions and rationale worth preserving
- Present a proposal to:
  1. Extract design decisions to relevant `design/` document
  2. Move performance findings to `benchmarks/` if applicable
  3. Archive the plan itself to `archive/completed/`
- Note: Plans often contain valuable insights beyond just implementation steps

**When you notice inactive/abandoned plans:**
- Evaluate if plan contains useful design decisions or learnings
- Present a proposal to extract valuable content before archiving
- Archive to `archive/abandoned/` with note about why it was discontinued

**When a design becomes outdated:**
- Identify what superseded it and document the evolution
- Present a proposal to archive with deprecation note
- Check if CLAUDE.md needs updates to reflect new approach

**When benchmarks age:**
- Consider if historical data is useful for trend analysis
- Present a proposal to move to `archive/old_benchmarks/` with date context

### README Maintenance

**After any memory update:**
- Check if `memory/README.md` directory index needs updating
- Update file listings when adding/moving/archiving documents
- Keep the index synchronized with actual directory structure
