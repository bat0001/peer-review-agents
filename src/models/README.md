# Models

Primary model families in this repo:

- `dense`: standard dense MLP
- `expert_choice`: unified expert-choice family (optional shared expert + optional chunked top-k)
- `token_choice`: token-choice baseline using vendored ScatterMoE kernels (`shared_expert` toggles shared mode)

## Core Files

- `model_base.py`: GPT backbone + model-type dispatch
- `expert_choice.py`: unified expert-choice wrapper
- `token_choice.py`: token-choice wrapper
- `engines/engine.py`: default expert engine
- `engines/parallel_experts_manual.py`: expert-parallel engine

## Routing Modes

- `topk`: default training route selection
- `threshold`: causal route selection used at eval/inference (and optionally in training)
