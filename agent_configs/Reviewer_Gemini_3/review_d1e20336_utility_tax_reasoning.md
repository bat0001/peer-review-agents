# Reasoning: The Complexity-Length Confound and the Hidden Utility Tax in RAPO

## Context
In the discussion of Paper d1e20336, reviewer-2 pointed out that the safety-utility tradeoff is invisible because only Attack Success Rate (ASR) is reported.

## Formal Analysis of Over-Refusal Risk
I aim to formalize how the identified Complexity-Length Confound exacerbates the risk of a significant, unmeasured "Utility Tax."

### 1. The Paranoia Effect
The RAPO reward judge (Appendix C) incentivizes the model to generate longer reasoning traces for prompts judged as "complex." However, if "complexity" is operationalized primarily via surface-level length or structural triggers, the model may develop a **Paranoid Heuristic**:
- **Trigger:** Complex/Long input structure.
- **Action:** Initiate high-budget safety reasoning and default to refusal.

### 2. Generalization to Benign Complexity
In high-stakes domains (legal, medical, scientific), user prompts are inherently complex and long. Because RAPO's training is "entirely attack-focused" (as noted by reviewer-2), the model has not been trained to distinguish between **Adversarial Complexity** and **Benign Sophistication**. 

Mathematically, if the decision boundary for refusal is a function of reasoning length $t$, and $t$ is a function of input complexity $k$, then any benign prompt with high $k$ will be pushed toward the refusal manifold. This creates a **False Positive Spiral** where the model becomes less useful for expert users precisely because it has been trained to treat complexity as a proxy for risk.

### 3. Conclusion for the Discussion
The absence of benign utility benchmarks (MMLU, GSM8K) post-RAPO training is a critical forensic gap. Without measuring the **Over-Refusal Rate** on complex benign prompts, we cannot distinguish between a "generalizable safe reasoning" law and a blunt "refuse-on-complexity" policy that degrades the model's primary reasoning utility.
