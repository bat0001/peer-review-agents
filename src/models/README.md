# Models

Primary model families in this repo:

- `dense`: standard dense MLP
- `gec`: routed experts only
- `gec_shared`: routed experts + one always-on shared expert
- `ec_shared`: chunked routing variant
- `scattermoe_tc` / `tc_shared`: token-choice baselines using vendored ScatterMoE kernels

## Core Files

- `model_base.py`: GPT backbone + model-type dispatch
- `gec.py`: GEC wrapper
- `gec_shared.py`: GEC shared wrapper
- `scattermoe_tc.py`: token-choice wrappers
- `engines/engine.py`: default expert engine
- `engines/parallel_experts_manual.py`: expert-parallel engine

## Routing Modes

- `topk`: default training route selection
- `threshold`: causal route selection used at eval/inference (and optionally in training)
