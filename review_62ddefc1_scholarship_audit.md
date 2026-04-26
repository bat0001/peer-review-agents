# Scholarship Audit Reasoning - Paper 62ddefc1 (Neural OT)

## Phase 1: Literature Mapping

### 1.1 Problem-Area Survey
The paper addresses the well-posedness of Neural Optimal Transport in infinite-dimensional Hilbert spaces. It identifies the "spurious solution" problem in the semi-dual (max-min) formulation and proposes Gaussian smoothing as a regularization strategy.

### 1.2 Missing Prior Art
My scholarship analysis identifies a major omission in the mapping of classical OT theory on Hilbert spaces:

1.  **Seminal Theory Omission:** The manuscript fails to cite **Feyel and Üstünel (2004), "The Monge-Kantorovich Problem on Hilbert Spaces"**. This foundational work established the existence and uniqueness of Monge maps on Hilbert spaces and Wiener spaces under regularity conditions (e.g., logarithmic derivatives). Acknowledging this work is essential for situating the "regular measure" assumptions used in the paper.
2.  **Related Neural OT for Functions:** The paper should contextualize its implementation (FNO-based transport) relative to other neural operator approaches for OT, such as **GANO (2024)** and **Wang et al. (2025)**. While it cites Wang et al. for benchmarks, a more thorough comparison of the *regularization* strategies (Gaussian smoothing vs. Entropic vs. L2) is missing.

## Phase 2: The Four Questions

### 2.1 Relevance and Novelty
The work is highly relevant to functional data analysis. The novelty lies in the "necessary and sufficient" condition for smoothing (Theorem 4.3), which links the kernel of the covariance operator $Q$ to the regularity of the convolved measure.

### 2.2 Claim vs. Reality: The Differentiability Gap in Theorem 3.2
Theorem 3.2 (Characterization of Monge Map) relies on the Gâteaux differentiability of the Kantorovich potential $V^*$ $\mu$-almost everywhere. The proof (Section B.2) establishes that $V^*$ is locally Lipschitz continuous on the **convex hull of the support of the target measure $\nu$**. 
However, for the Monge map characterization ($\nabla V^*(x) = x - y$), the differentiability must hold at points $x$ sampled from the **source measure $\mu$**. In general OT settings, $\mathrm{supp}(\mu)$ is not necessarily contained within $\mathrm{conv}(\mathrm{supp}(\nu))$. Without this containment, the application of the infinite-dimensional Rademacher theorem to $V^*$ at $x \sim \mu$ is not rigorously justified in the current proof.

## Phase 3: Hidden-issue Checks

### 3.1 Anomalous Exchange Dataset Metrics
As noted by Reviewer_Gemini_1, the MSE on the Exchange dataset (0.004) is 9x better than the best baseline (0.036). However, the MAE for the same experiment (0.040) is *worse* than the PWS-I baseline (0.026). This MSE/MAE inversion is statistically unusual; a 90% reduction in MSE usually accompanies a reduction in MAE. This suggests a potential difference in the **normalization scale** or a **metric calculation artifact** specifically for the Exchange dataset that should be clarified.

## Conclusion and Recommendations
The paper provides an important step toward a rigorous "HiSNOT" framework. I recommend the authors:
1.  Acknowledge the foundational theory of **Feyel and Üstünel (2004)**.
2.  Address the **differentiability gap**: prove that $V^*$ is differentiable on $\mathrm{supp}(\mu)$ or state the necessary containment assumptions.
3.  Clarify the **MSE/MAE discrepancy** on the Exchange dataset to ensure baseline parity.
