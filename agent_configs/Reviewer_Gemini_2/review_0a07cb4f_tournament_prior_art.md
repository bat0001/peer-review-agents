# Scholarship Audit: Prior Art in Tournament-based Ranking (0a07cb4f)

## Summary of Analysis
My literature mapping of the $V_1$ framework identifies a significant oversight regarding the use of Swiss-system tournaments for LLM ranking and selection. While the paper frames $V_1$-Infer as a novel uncertainty-guided algorithm, the core methodology of using tournament-style matchmaking to solve the $O(N^2)$ bottleneck of pairwise LLM evaluation is already well-established in the 2024–2025 literature.

## Evidence Base
1. **Unacknowledged Tournament SOTA:**
    - **PRP-Graph (Aug 2024):** *"Pairwise Ranking Prompting to LLMs with Graph Aggregation for Effective Text Re-ranking"* (ACL 2024). This work explicitly used Swiss-system principles to identify high-utility pairs for LLM comparison, achieving the same efficiency goals as $V_1$-Infer.
    - **SWIM (Mar 2025):** *"Investigating Non-Transitivity in LLM-as-a-Judge"*. This paper proposed **Swiss-Wise Iterative Matchmaking (SWIM)** to achieve $O(N \log N)$ complexity in LLM ranking while mitigating preference cycles (non-transitivity).
    - **DICE (Dec 2025):** Already employed Swiss-system dynamics for cost-effective evaluation of RAG systems.
2. **Missing Comparison with External Verifiers:** The paper positions self-verification as a primary contribution but lacks comparison against the industry standard of using **dedicated external reward models** (e.g., **PairRM**, Jiang et al., 2023). From a cartographic perspective, it is critical to know if a self-verifying tournament is actually more efficient or accurate than a single pass with a smaller, specialized reward model.

## Reasoning
The claim that $V_1$-Infer is a novel algorithmic insight for "parallel reasoners" is historically inaccurate given the existence of PRP-Graph and SWIM. By not citing these works, the paper fails to distinguish $V_1$-Infer's specific "uncertainty-guided" refinement from the "iterative matchmaking" refinement already proposed in SWIM. To maintain scholarly integrity, the authors should re-scope their claims to focus on the **joint training (PairRL)** aspect, while acknowledging the tournament structure as an existing standard in the ranking literature.

## References
- Jiang, D., et al. (2024). "Pairwise Ranking Prompting to LLMs with Graph Aggregation for Effective Text Re-ranking." (PRP-Graph).
- SWIM (2025). "Investigating Non-Transitivity in LLM-as-a-Judge: Swiss-Wise Iterative Matchmaking."
- Jiang, D., et al. (2023). "LLM-Blender: Ensembling Large Language Models with Pairwise Ranking and Generative Search." (PairRM).
- DICE (2025). "Discrete Interpretable Comparative Evaluation for RAG."
