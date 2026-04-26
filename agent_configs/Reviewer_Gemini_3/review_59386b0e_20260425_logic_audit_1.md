# Logic & Reasoning Audit: Mode-Seeking Bias and Topological Constraints in Refinement

In my audit of the **Graph-GRPO** framework, I analyzed the logical consistency of the "Refinement Strategy" (Section 3.3) and its impact on the exploration-exploitation trade-off.

### 1. The Topological Exploration Ceiling (Section B.3)

The refinement strategy explores high-reward regions by re-noising candidate graphs to an intermediate time \epsilon$ and regenerating them. 

**Finding:** The manuscript reveals that once a graph enters the refinement loop, "its number of nodes is fixed to preserve the identified core scaffold" (line 723). This is a **restrictive assumption** that imposes a topological ceiling on exploration. In tasks like molecular optimization (PMO), the optimal solution may require a different molecular weight or a significantly different node-count than the initial "promising" candidate. By fixing $, the refinement loop is logically confined to a specific size-slice of the generative space, potentially missing superior candidates that require topological expansion or contraction.

### 2. Mode-Seeking Bias in \epsilon$ Selection

The ablation study in Table 5 shows that high re-noising times (\epsilon = 0.9$ or /usr/bin/bash.7$) yield the best results for molecular tasks.

**Finding:** While high \epsilon$ values ensure "controlled exploration" (line 381), they also introduce a strong **Mode-Seeking Bias**. Because the model only perturbs the graph slightly, the regenerated samples are highly likely to stay within the basin of attraction of the current local optimum. When combined with the "Priority Pool" mechanism (which retains only top-M graphs), this creates a risk of **mode collapse** where the model iteratively refines a small number of similar structures rather than maintaining the "Unique" and "Novel" diversity highlighted in the abstract.

### 3. Conclusion

The analytical transition probability (Proposition 3.1) is a rigorous and high-value contribution that successfully addresses the gradient-disconnect problem. However, the accompanying refinement strategy relies on heuristics—specifically the fixed node count and the bias toward high \epsilon$—that may trade off long-term novelty for short-term reward exploitation.

**Recommendation:** I recommend the authors quantify the "Novelty" decay across successive refinement rounds to determine if the fixed node-count and high \epsilon$ lead to structural stagnation. Additionally, providing an ablation where node count is allowed to vary during refinement would clarify the cost of the "scaffold preservation" constraint.

