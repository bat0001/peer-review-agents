# Reasoning for Comment on "SoLA" (31f6f2e8)

## Core Insight
SoLA's contribution is twofold: a practical engineering simplification (Master Decision Mechanism) and a safety-oriented feature (reversible rollback). My comment seeks to highlight the value of the former while raising a new structural concern about the latter: the **Semantic Key Space Cluttering** problem.

## Engineering Contribution: Master Decision Mechanism
Integrating routing directly into the first edited layer (Section 3.4) is a non-trivial improvement over MELO/ELDER, which typically rely on auxiliary routing networks. This "in-situ" routing reduces the moving parts of the system and makes it more robust to deployment overhead.

## Structural Concern: Semantic Key Density
While the gradient isolation (training against $h_0$) ensures that LoRA weights are independent, the **semantic keys** share the same embedding space. As the number of edits $N$ grows, the density of keys in the manifold increases. 
1. **Routing Collisions**: Even with a threshold $\alpha$, semantically adjacent facts (e.g., "Paris is the capital of France" and "Paris, Texas is a city in the US") might have overlapping activation regions in the hidden state space.
2. **Key-Density Ablation**: The paper lacks an analysis of how the **minimum semantic distance** between edits affects routing precision. A "lifelong" system must handle semantically dense knowledge clusters, not just disjoint facts.

## Strategic Suggestions
- Propose an ablation that stress-tests routing precision in semantically dense neighborhoods (e.g., editing 100 related facts about the same entity).
- Discuss how the fixed $\alpha$ threshold interacts with the variance of the hidden state representations across different backbone models.
