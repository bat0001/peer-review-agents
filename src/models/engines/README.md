# Expert Engines

This module keeps two engine implementations intentionally.

## 1) `ExpertEngine` (`engine.py`)

Default routed-expert path for single-GPU / data-parallel execution.

Responsibilities:
- router logits and token selection (`topk` / `threshold`)
- per-expert MLP compute
- cutoff EMA tracking
- returns pre-scatter expert outputs + routing metadata

## 2) `ParallelExperts` (`parallel_experts_manual.py`)

Expert-parallel path with explicit cross-rank dispatch/combine.

Responsibilities:
- global routing decisions
- all-to-all payload exchange
- local expert compute
- combine back to source ranks

## Selection Rule

Model wrappers (`gec.py`, `gec_shared.py`) choose by `config.expert_parallel`:

- `false` -> `ExpertEngine`
- `true` -> `ParallelExperts`

## Why Keep Both

Keeping EP logic separate prevents communication concerns from complicating the standard engine path.
