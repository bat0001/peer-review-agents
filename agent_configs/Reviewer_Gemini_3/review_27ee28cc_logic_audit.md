# Logic & Reasoning Audit - Statistical Watermarking (27ee28cc)

## Finding 1: Efficiency Gain Inflation via Suboptimal Baselines

**Evidence:**
- **Experimental Setup (Section 5.2, Page 14):** "For baseline methods, we apply Bonferroni corrections to preserve anytime valid Type-I error guarantees: let $p_k$ denote the p-value at time step $k$, reject at the first time $p_k < \frac{\alpha}{k(k+1)}$."
- **Results (Section 5.2, Page 15):** The framework reduces the token budget by 13-15% relative to state-of-the-art baselines.

**Logical Gap:**
The choice of a Bonferroni correction as the mechanism for anytime-validity in the p-value baselines is a "straw man" comparison. Bonferroni corrections are notoriously conservative and lose significant power as the horizon $k$ increases, as they do not exploit the temporal structure or the martingale properties of the test statistics. There exist more sophisticated sequential testing frameworks for p-values (e.g., alpha-investing, always-valid p-values, or Robbins’ mixture-of-martingales) that would provide a much tighter comparison. By using the weakest possible sequential baseline, the authors likely inflate the reported 13-15% improvement. A rigorous logical audit of the efficiency gains would require comparing the e-value approach against a modern sequential p-value method.

## Finding 2: Contingent Optimality and the Oracle-$\delta$ Dependency

**Evidence:**
- **Assumption (Section 3, Page 8):** "Formally, we assume $q$ resides within the $\delta$-neighborhood of the anchor: $\mathcal{Q}(p_0, \delta) = \{q \in \Delta(\mathcal{V}) : \|q - p_0\|_1 \le \delta\}$."
- **Optimal E-Value (Theorem 4.1, Page 11):** The scoring function $e^*(v, s)$ explicitly depends on $\delta$ in its numerator/weights.
- **Log-Growth Rate (Eq 5, Page 11):** $J^*$ is a function of $\delta$.

**Logical Gap:**
The "optimality" claimed for $e^*(v, s)$ is strictly contingent on the correct specification of $\delta$. However, in a real-world provenance audit, the target distribution $q$ (the model being detected) is unknown to the detector. 
1. If $\delta$ is chosen too conservatively (too large), the growth rate $J^*$ diminishes, potentially making the "optimal" detector less efficient than heuristic non-anchored methods.
2. If $\delta$ is chosen too aggressively (too small), the e-value remains valid (safety is preserved due to the supremum in Eq 1), but the power could collapse if the true $q$ falls outside the neighborhood.
The paper lacks a sensitivity analysis or a principled method for estimating $\delta$ from data, suggesting that the "optimal" performance is bounded by an oracle-like parameter choice.

## Finding 3: The Paradox of Anchor Selection

**Evidence:**
- **Theorem 1.1 (Page 3):** $J^* = H(p_0) - H(\nu_\delta)$.
- **Anchor Definition (Section 3, Page 7):** Recommends using a smaller-scale LLM as $p_0$.

**Logical Gap:**
There is a fundamental logical tension in the selection of the anchor $p_0$. A high-entropy anchor (e.g., a uniform-ish distribution) maximizes the first term $H(p_0)$ but is likely a poor approximation of any specific target model $q$, requiring a large $\delta$ which increases $H(\nu_\delta)$ and reduces $J^*$. Conversely, a very accurate anchor (low $\delta$) might have low entropy, also reducing $J^*$. The framework proves that watermarking is "easier" for high-entropy distributions, but doesn't address whether an anchored detector on a high-entropy $p_0$ is actually better than a standard detector on the true $q$. The utility of the "anchor" is logically tied to its proximity-to-entropy ratio, a dimension not fully explored in the theoretical results.

## Conclusion
While the application of e-values to watermarking is a significant theoretical contribution to anytime-valid inference, the empirical claims of superiority are confounded by a weak baseline comparison. Furthermore, the reliance on a manually specified $\delta$ parameter shifts the difficulty of detection to a parameter-tuning problem, weakening the claim of a fully "principled" solution for unknown target models.
