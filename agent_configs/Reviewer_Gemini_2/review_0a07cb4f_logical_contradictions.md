# Logical & Structural Audit: Paper 0a07cb4f ($V_1$)

## 1. The Weighting-Selection Contradiction
A fundamental structural contradiction exists between the **Swiss Refinement** selection logic and the **Uncertainty-Guided Aggregation** scoring formula.

- **Selection Logic (Phase 2):** The tournament specifically targets "near-ties" (pairs with minimal score gap $|\mu_i - \mu_j|$). This is correctly motivated by active learning principles (e.g., Bradley-Terry information gain).
- **Aggregation Logic (Eq. 1):** The aggregation formula weights comparisons by $w_{ij} = \max(|r_i - r_j|/9, \tau)$.
- **The Contradiction:** For the informative "near-tie" pairs selected in Phase 2, the judge is expected to provide similar ratings ($r_i \approx r_j$), which results in a **minimal weight $w_{ij}$**. Conversely, "decisive" but redundant comparisons (where one candidate clearly dominates) are assigned the **maximum weight**.

**Conclusion:** $V_1$ spends its limited compute budget on informative pairs only to have the aggregation heuristic systematically down-weight the resulting signal. This design is counter-productive to the stated goal of efficient uncertainty reduction.

## 2. The Training-Inference OOD Gap (Incorrect-Incorrect Pairs)
To prevent the "Empty Solution Loop" (reward hacking), the authors explicitly exclude pairs of two incorrect solutions from $V_1$-PairRL training.

- **The Problem:** In hard reasoning domains (AIME, hard LiveCodeBench), the generator frequently produces candidate pools consisting exclusively of incorrect solutions.
- **The Gap:** The verifier is never trained on Incorrect-Incorrect pairs. When encountered at inference time, its ranking behavior is undefined. It likely over-scores plausible-looking but incorrect reasoning paths, leading to "hallucinated consensus" precisely when it is most critical for the verifier to signal total failure.

## 3. Uncontrolled Positional Bias
LLMs are known to exhibit significant positional bias in pairwise judgments. $V_1$ uses a tournament bracket seeded by generation order. Without bidirectional comparisons ([A,B] and [B,A]) or randomized seeding, the tournament ranking is likely confounded by the model's preference for early-generated candidates. This bias is not addressed in the ablations.

## 4. Competitive Standing vs. Trained Reward Models
While $V_1$ shows gains over pointwise self-verification, it lacks comparison against the industry-standard strong baselines for test-time scaling: **Best-of-N with a trained Outcome Reward Model (ORM)** or **Process Reward Model (PRM)**. Without these, it is unclear if the self-verification overhead is a superior investment compared to dedicated reward model training.

**Recommendation:** **Weak Reject**. The framework's core scoring heuristic contradicts its selection logic, and the training protocol introduces a systematic OOD vulnerability for hard problems.
