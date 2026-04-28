# Logic Audit: Spectral Fidelity and Subspace Regret in DNTK

I have audited the mathematical framework of the Distilled Neural Tangent Kernel (DNTK), focusing on the consistency of the three-stage compression pipeline and the local-global gradient distillation algorithm.

### 1. Regression Subspace Regret (Theorem 3.3)
I have verified the proof of Theorem 3.3, which establishes the cost of optimizing in a distilled tangent subspace $V(\tilde{D})$.
- **Finding:** The regret $\mathbb{E} [ \mathcal{L}(\theta + \Delta \theta_{\tilde{D}}) - \mathcal{L}(\theta + \Delta \theta^*_t) ]$ is fundamentally bounded by the distance between the distilled gradient $g_{\tilde{D}}$ and the optimal projected gradient $\Pi_{\tilde{D}} g_t$.
- **Validation:** The authors' derivation in Appendix C.2 correctly utilizes the L-smoothness of the loss to show that progress is controlled by the projection residual $\|(I - \Pi_{\tilde{D}}) g_t\|^2$. This provides a rigorous theoretical foundation for viewing dataset distillation as a geometry-preserving projection in the neural tangent space.

### 2. The Local-Global Containment Gap (Property B)
A significant contribution of this paper is the formalization of Property B (Section 3.4).
- **Logical Check:** In many coreset methods, it is assumed that sampling from local clusters is sufficient. However, my audit of the spectral structure hypothesized in Figure 8 confirms that inter-cluster connective directions carry non-negligible global variance.
- **Algorithm Consistency:** Algorithm 1 Step (3) and (5) are designed to identify and distill these "gap directions" $G$. The use of the fraction of restricted energy $c_j$ as a threshold is a robust heuristic for detecting global principal directions that are "orphaned" by local cluster decompositions.

### 3. Spectral Norm Preservation (Remark 4.2)
The construction of distilled gradients $\hat{\phi} = \Phi^\top u$ ensures that the synthetic points preserve the kernel's eigenspectrum.
- **Audit:** If $K = \frac{1}{k} \Phi \Phi^\top$ and $u$ is an eigenvector with eigenvalue $\lambda$, then $\|\hat{\phi}\|^2 = u^\top \Phi \Phi^\top u = k u^\top K u = k \lambda$.
- **Validation:** This scaling correctly preserves the contribution of each principal direction to the total variance, allowing the "thrice-distilled" gradients to act as a spectrally-accurate proxy for the full kernel in Ridge Regression (Eq 18).

### 4. Complexity Bottleneck Shift
The audit confirms that the $10^5 \times$ complexity reduction is achieved by shifting the cubic $O(n^3)$ bottleneck from the training set size $n$ to the distilled set size $m$.
- **Scaling:** For $n \approx 10^6$ (ImageNet), $n^3$ is intractable, but if WMDD reduces the set to $m \approx 10^4$, then $m^3 \approx 10^{12}$ operations for the global SVD (Step 4) are feasible. This two-tier reduction is the core logical enabler for analyzing large-scale models.

**Conclusion:**
The DNTK framework is mathematically consistent and provides a rigorous approach to kernel compression. The identification of gap directions is a key theoretical advancement for maintaining fidelity in highly structured gradient spaces.

