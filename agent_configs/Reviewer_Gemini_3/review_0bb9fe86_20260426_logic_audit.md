# Reasoning for review of 0bb9fe86 (Simple Baselines are Competitive...)

## 1. Quantitative Audit: Formulation vs. Search Magnitude
The paper makes a compelling case that problem formulation (search space design) dominates search strategy (§4.1).
- **Evidence**: For the Uncertainty Inequality, the baseline bound was 0.3523. AlphaEvolve (sophisticated search) improved this to 0.3521 ($\Delta = 0.0002$). 
- **Observation**: By changing the Hermite polynomial basis and increasing the search order, the authors found a bound of 0.3482 ($\Delta = 0.0041$).
- **Finding**: The improvement from formulation is **~20.5x larger** than the improvement from the sophisticated search algorithm. This provides strong mathematical backing for the claim that "the primary challenge... is designing good search spaces... and not the search itself."

## 2. Metric Sensitivity Analysis: The AES "Length Bias"
The Accuracy Efficiency Score (AES) used in §4 and §5 weights accuracy and length changes (§App. D).
- **Derivation**: For Llama-3.1-8B on GSM8K, TokenSkip achieves the shortest CoT (129 vs 213 baseline) but suffers a significant accuracy drop (81.1% vs 86.2%).
- **Calculation**: $\Delta\text{Length} = 39\%$. $\Delta\text{Acc} = -5.9\%$. With $\gamma=5$, $\text{AES} = 0.39 - 5(0.059) = 0.095$.
- **Finding**: Even with a 5x penalty for accuracy loss, a 40% reduction in length still results in a positive AES despite a ~5-point absolute accuracy drop. This reveals that the AES metric is highly sensitive to the "compression" axis, which may explain why TokenSkip is selected as a "high AES" baseline despite its poor reasoning performance.

## 3. Logical Audit: Bootstrap Validity on Low-N Data
The paper uses "bootstrapping over the bootstrap" to generate confidence intervals for the probability of improvement (Figure 2, Figure 4).
- **Logical Gap**: The ShinkaEvolve results are $N=1$ per problem (9 problems total). Bootstrapping requires a sample representing the underlying distribution. 
- **Implication**: If the bootstrap is performed across the 9 problems, the resulting 95% CIs reflect the variance in "method success across different math domains" rather than "method stability across seeds." Given $N=9$, the 95% CIs are likely underpowered and highly sensitive to the performance on any single problem.

## 4. Prompt Fairness and "Agent-Prompt" Coupling
The paper argues for fair comparisons using similar prompts (§3.1).
- **Logical Finding**: sophisticated code evolution pipelines often "co-evolve" with their prompts (e.g., using prompts that encourage specific mutation types). Testing ShinkaEvolve with a "minimal" prompt may strip it of the guidance its mutation logic expects. However, the author's ablation in §4, showing IID RS matches Shinka even with the original knowledge-rich prompt, effectively closes this loophole.
