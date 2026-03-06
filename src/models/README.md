# Models

Primary model families in this repo:

- `dense`: standard dense MLP
- `expert_threshold`: unified routed-expert family implemented by `ExpertThresholdChoiceMLP`
- `token_choice`: token-choice baseline using vendored ScatterMoE kernels (`shared_expert` toggles shared mode)

## Core Files

- `model_base.py`: GPT backbone + model-type dispatch
- `expert_threshold_choice.py`: unified routed-expert wrapper implementing both EC and ET
- `token_choice.py`: token-choice wrapper
- `engines/engine.py`: default expert engine
- `engines/parallel_experts_manual.py`: expert-parallel engine

## Routing Modes

- `topk`: expert-choice routing, including ET warmup
- `threshold`: threshold routing used for causal ET execution
