# Forensic Audit: The Information Destruction Paradox in V1

My forensic audit of the **V1** framework identifies a fundamental structural contradiction between the training objective (V1-PairRL) and the inference-time algorithm (V1-Infer).

### 1. The Paradox of Saturated Rewards
The V1-Infer algorithm relies on **Uncertainty-Guided Score Aggregation** (Section 4, Page 6), where comparisons are weighted by the magnitude of the rating difference:
1578438w_{ij} = \max\left(\frac{|r_i - r_j|}{9}, \tau\right)1578438
This mechanism is designed to let high-confidence judgments (large $|r_i - r_j|$) dominate the ranking.

However, the **V1-PairRL** training objective (Section 5.2, Equation 4, Page 11) implements a **Sparsity Threshold** using an indicator function:
1578438r_{\text{verif}} = \frac{1}{2} \sum_{i \in \{A, B\}} \mathbb{I}(|v_i - y_i| \leq 0.2) \cdot (1 - |v_i - y_i|)1578438
This objective explicitly rewards the model for moving its scores $ as close as possible to the binary ground truth  \in \{0, 1\}$. 

**The Finding:** Success in training (maximizing {\text{verif}}$) directly results in **score saturation**. If the model successfully learns to score all correct solutions near 1.0 and all incorrect solutions near 0.0, the term $|r_i - r_j|$ will approach 0 for any pair of the same class (e.g., two correct solutions). This forces the weights {ij}$ to collapse to the floor value $\tau$, effectively transforming the "uncertainty-guided" aggregation into a simple, unweighted average.

### 2. Impact on Fine-Grained Discrimination
The authors claim that V1-Infer excels at identifying subtle correctness differences, such as the SWE-bench examples (Section G, Page 31). However, in a co-evolved model that has achieved high accuracy, most candidate pairs will be **Correct-Correct (C-C)**. Because the RL objective (Eq 4) is strictly pointwise and rewards saturation at 1.0, the model is disincentivized from maintaining the intermediate "confidence gradients" that the $|r_i - r_j|$ weighting requires to distinguish a minimal, robust fix from a complex, regression-prone one.

### 3. Conclusion
The Sparsity Threshold, while intended to prevent "Safe Bet" collapse, inadvertently destroys the very signal that the inference-time tournament relies on for informed ranking. The "discriminating power" observed in experiments may be a transient property of partially-trained models rather than a stable feature of the converged architecture.

**Recommendation:**
The authors should report the distribution of $|r_i - r_j|$ for C-C and C-I pairs throughout the RL training process to verify if the "Uncertainty-Guided" signal is indeed being preserved or destroyed by the sparsity reward.

