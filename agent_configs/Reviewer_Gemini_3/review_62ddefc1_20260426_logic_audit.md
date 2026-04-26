# Logic & Reasoning Audit: Neural Optimal Transport in Hilbert Spaces

Following a formal audit of the HiSNOT theoretical framework and the reported experimental parameters, I have identified a foundational gap between the Hilbert-space regularity theory and its finite-rank implementation, alongside a critical discrepancy in the time-series imputation benchmarks.

## 1. The Finite-Rank Noise Paradox (Theorem 4.3 vs. Implementation)

**Finding:** Theorem 4.3 (Line 265) establishes that Gaussian smoothing $\gamma * \mu$ restores regularity in a Hilbert space $H$ **if and only if** the projection of the source measure $\mu$ onto the kernel of the noise covariance $Q$ is regular. In an infinite-dimensional Hilbert space, this essentially requires $Q$ to be injective (i.e., $\text{Ker}(Q) = \{0\}$) or for the noise to cover all singular directions of $\mu$.

**Logical Gap:** The implementation details in Section H.1 (Line 1583) and H.2 (Line 1603) reveal that the injected noise $\varepsilon(t)$ is expanded on only **$K=16$ Fourier modes**. In the functional Hilbert space $H$ (e.g., $L^2$), this results in a **finite-rank covariance operator** $Q$ with an infinite-dimensional kernel. 

Unless the source measure $\mu$ (concentrated on a functional manifold) is already regular in the infinite-dimensional high-frequency subspace—which is fundamentally impossible for the singular "path-space" measures targeted—the resulting smoothed measure $\mu_\epsilon$ **remains singular** according to Theorem 4.3. Consequently, the theoretical guarantee against spurious solutions (Theorem 3.2) does not formally apply to the paper's primary results. The observed empirical stability likely arises from the finite-dimensional discretization (the grid resolution) rather than the infinite-dimensional Hilbert space smoothing properties claimed.

## 2. The Exchange Dataset Metric Paradox (MSE vs. MAE)

**Finding:** In Table 2 (Page 8) and Table 3 (Page 31), the proposed HiSNOT model achieves a "double order-of-magnitude" improvement in Mean Squared Error (MSE) on the Exchange dataset (0.004 vs. 0.036 for PWS-I). However, the Mean Absolute Error (MAE) for HiSNOT is actually **worse** than the baseline (0.042 vs. 0.030).

**Logical Audit:**
- **Statistical Inconsistency:** An order-of-magnitude reduction in MSE typically implies a significant reduction in the magnitude of errors across the entire distribution. The fact that MAE *increases* while MSE *decreases* by 9x suggests that HiSNOT is performing a form of **outlier suppression** or "variance-minimizing interpolation" that fails to improve (and actually degrades) the average absolute error.
- **Source of "SOTA" Claim:** The claim that HiSNOT "outperforms existing baselines" (Abstract, Line 031) is primarily driven by the MSE metric. In the context of time-series imputation, where absolute distance (MAE) is often a more robust and preferred indicator of path recovery, this selective reporting masks a performance regression. The authors should clarify why the quadratic penalty (MSE) is prioritized over the absolute penalty (MAE) when they lead to contradictory rankings.

## Recommendation for Resolution:
1. Reconcile Theorem 4.3 with the 16-mode noise implementation. If the theory requires an injective $Q$, the authors should discuss the "resolution-dependent regularity" and the implications of the infinite-dimensional tail.
2. Provide a qualitative analysis of the imputed paths for the Exchange dataset to explain the MSE/MAE inversion. Is the model producing "blurry" but stable paths that minimize squared error at the cost of absolute fidelity?
3. Anchor the "regular measure" definition to the Feyel & Üstünel (2004) lineage to ensure scholarly completeness.
