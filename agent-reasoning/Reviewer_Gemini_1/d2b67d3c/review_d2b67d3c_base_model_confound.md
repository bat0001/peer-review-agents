# Reasoning for Base Model Confound (RL Math) - Paper d2b67d3c

## Finding
The "shortcut" behavior observed in the RL experiments (Section 3.2), where models with small budgets learn to skip steps, may be a confound of using a pre-trained "Instruct" model (\texttt{Qwen2.5-1.5B-Instruct}). This complicates the claim that self-iteration mechanistically shifts the solution away from shortcuts learned *during* training.

## Evidence
1. **Model Selection:** The study uses \texttt{Qwen2.5-1.5B-Instruct}, which has already undergone substantial SFT and RLHF for instruction following and reasoning.
2. **Shortcut Nature:** The observed "shortcut" (Fig 3 and Appendix A.2.2) is a model that outputs the answer with minimal reasoning tokens. This is a behavior that "Instruct" models are already capable of (and often biased towards, depending on the system prompt and previous training).
3. **Transition Dynamics:** Figure 3 shows that for small budgets, the reward rises only when the response length *drops*. This suggests the model is reverting to its pre-existing "direct answer" mode to maximize reward within the constrained budget, rather than learning a new, non-generalizable mechanism from scratch.
4. **Lack of Ablation:** Without an experiment using a non-instruct "Base" model, it is impossible to distinguish between (a) a fundamental property of reasoning length scaling and (b) an artifact of the model's pre-existing instruction-following repertoire.

## Recommendation
To isolate the effect of reasoning length on shortcut selection, the authors should repeat the experiment using a base model that has not been fine-tuned for instructions (e.g., \texttt{Qwen2.5-1.5B}). This would demonstrate whether the "shortcut" mechanism is actually learned from the reward signal or merely retrieved from the model's pre-training.
