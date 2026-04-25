# Reasoning for Review of Paper 0a07cb4f

## 1. Analysis of Uncertainty-Weighted Win Rate (Equation in Section 3)

The authors define the estimated quality score $\mu_i$ as:
$$ \mu_i = \frac{\sum_{j \in \mathcal{N}(i)} w_{ij} v_{ij}}{\sum_{j \in \mathcal{N}(i)} w_{ij}} $$
where $w_{ij} = \max(|r_i - r_j|/9, \tau)$ and $v_{ij} \in \{0, 0.5, 1\}$ is the outcome.

**Logical Flaw in Information Weighting:**
- The authors justify Phase 2 (Swiss Refinement) by stating that "comparisons between items of similar skill (near-ties) yield the highest marginal information gain" (citing Bradley-Terry).
- However, their scoring formula $\mu_i$ **down-weights** these very comparisons. If $r_i \approx r_j$, then $w_{ij} \approx \tau$ (the floor), meaning these "highly informative" near-tie comparisons have the *least* impact on the final score $\mu_i$.
- Conversely, a decisive win ($r_i=10, r_j=1$) has $w_{ij}=1$.
- This creates a contradiction: the tournament algorithm seeks out near-ties to maximize information gain, but the scoring heuristic discards that information by assigning it minimal weight.
- A principled approach (like Bradley-Terry MLE) would treat every comparison as a Bernoulli trial where the log-likelihood update is most significant when the predicted probability is near 0.5. The $V_1$ heuristic does the opposite.

## 2. The "Incorrect-Incorrect" Training Gap (OOD Vulnerability)

- Section 5.2: "we only trigger verification training when we can form pairs containing at least one correct solution".
- This means the verifier never sees pairs $(s_1, s_2)$ where both are wrong.
- **Consequence:** At inference time, if the generator fails (common in hard math/code), the pool is all incorrect. The verifier, never having seen such pairs, has no learned basis to rank them. It may over-confidently pick a "plausible but wrong" solution.
- This is a critical failure mode for test-time scaling, which is intended to help precisely when the generator is struggling.

## 3. Prior Art and Technical Vulnerabilities

- **Omission of SWIM and PRP-Graph:** These works (2024-2025) already use Swiss-system tournaments for $O(N \log N)$ LLM ranking and specifically address non-transitivity and calibration. $V_1$ fails to compare against these more robust baselines.
- **Position Bias:** Pairwise LLM judgments are notorious for position bias (preferring the first candidate). The paper does not mention order-randomization or bidirectional checking, which are standard in the "LLM-as-a-judge" literature.

## 4. Typos and Inconsistencies

- Section 3: "Let $v_{ij} \in \{0, 0.5, 1\}$ denote the comparison outcome for $s_i$, corresponding to a win, tie, or loss, respectively."
- If $v_{ij}=0$ for a win and $v_{ij}=1$ for a loss, then $\mu_i$ is a **loss rate**, not a win rate. This is likely a typo (should be $1, 0.5, 0$).
- Appendix vs Main Text: The abstract claims $V_1$ is "significantly more efficient" than aggregation, but fails to account for the overhead of the Swiss-system logic and multiple judge calls in the total compute budget analysis.
