# Logic & Reasoning Audit: High-Frequency Bias in Feature Recovery - SynthSAEBench (2116346c)

Following a logical audit of the SynthSAEBench evaluation protocol, I have identified a structural bias in the feature recovery metrics regarding the handling of long-tail distributions.

**1. Dimensional Mismatch (Section 5.1):** The benchmark model (SynthSAEBench-16k) contains $N = 16,384$ ground-truth features, but the paper recommends training SAEs with a width of $L = 4,096$. This 4:1 ratio ensures that at least 75% of the features cannot be uniquely represented.

**2. Metric Formulation (Equation 17):** The Mean Correlation Coefficient (MCC) is defined using optimal bipartite matching between SAE decoder columns $w_j$ and ground-truth features $d_i$:
$$MCC = \frac{1}{\min(L, N)} \sum_{(i,j) \in \text{matching}} |w_j^\top d_i|$$
Because $L \ll N$ ($4,096 \ll 16,384$), the metric is normalized by $L$. This means it only measures the quality of the top $4,096$ matches.

**3. The Zipfian Recall Gap:** The features fire according to a **Zipfian distribution** with exponent 0.5 (Line 295). This implies a high disparity in firing frequency (a ~128x range). Under current training objectives (MSE + Sparsity), SAEs naturally prioritize high-frequency features that contribute most to reconstruction variance. 
- The MCC metric, by focusing only on the $L$ matched pairs, effectively **ignores the 12,288 features in the long tail**.
- This creates a **High-Frequency Bias**: an SAE could achieve a high MCC score by perfectly recovering only the most frequent 25% of features, while providing zero interpretability for the remaining 75%. 

In a real-world interpretability context, rare features (e.g., specific factual knowledge) are often the most valuable. By structural design, SynthSAEBench measures "top-k recovery quality" rather than "dictionary completeness," which may lead researchers to optimize for high-frequency signal at the expense of capturing the full breadth of the latent space.

**Recommendation:** The authors should introduce a "Feature Recall" metric that measures the fraction of the full $N$ ground-truth features recovered above a certain similarity threshold, normalized by $N$ rather than $L$, to expose the capture rate of long-tail semantics.
