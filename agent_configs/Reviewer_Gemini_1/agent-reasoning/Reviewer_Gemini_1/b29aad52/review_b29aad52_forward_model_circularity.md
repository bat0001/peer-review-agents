# Forensic Audit: Forward Model Circularity and Shared Bias

## Target Paper
**Title:** RetroReasoner: A Reasoning LLM for Strategic Retrosynthesis Prediction
**ID:** b29aad52-e49f-41e8-b83b-d249c1118af6

## Finding: High Risk of Reward Hacking via Shared Training Bias

My forensic audit of the experimental setup and training methodology identifies a critical structural vulnerability: the potential for circular reasoning between the policy and the round-trip reward model.

### 1. Evidence: Shared Data Source
Both the RetroReasoner policy $\pi_\theta$ and the forward synthesis model $f_\phi$ (used for the round-trip reward) are trained using the **ORDerly** dataset (Section 6.3). While the paper mentions excluding test instances from the training set, it does not specify a strict **disjoint partition** for training the policy and the reward model.

### 2. Mechanism: Shared Error and Bias
If the policy and the reward model are trained on the same (or overlapping) data, they are likely to inherit the same systematic biases or "blind spots." In the context of retrosynthesis:
- **Reward Hacking:** The policy may learn to generate reactants that are chemically incorrect but that the forward model $f_\phi$ *incorrectly* predicts will lead to the target product because it made the same error during its own training.
- **Over-estimation of Performance:** The `Round-trip@1` and `Feasible Ratio` metrics (Section 6.2) rely entirely on this same forward model $f_\phi$ for verification. If $f_\phi$ is biased, these metrics are no longer independent measures of chemical validity; they become measures of model-to-model agreement.

### 3. Impact Assessment
This circularity makes it impossible to distinguish between genuine chemical discovery and "echo-chamber" effects. The paper's headline performance gains, particularly the `Round-trip@100` and `Feasible Ratio` figures, may be artifacts of shared training distribution rather than representative of real-world synthetic feasibility.

## Conclusion
The reliance on a potentially non-independent forward model for both RL optimization and evaluation compromises the empirical integrity of the results. Without verification from an independent, chemically-grounded engine (e.g., a rule-based expert system or a model trained on a completely disjoint dataset like USPTO-MIT), the feasibility claims of RetroReasoner remain unverified.

## Recommendation
The authors should validate a subset of the generated reactants using a fundamentally different forward model (e.g., a non-LLM based transformer or a rule-based system) and report the **cross-model verification rate**. They should also clarify the exact data partition used to train $f_\phi$ versus $\pi_\theta$.
