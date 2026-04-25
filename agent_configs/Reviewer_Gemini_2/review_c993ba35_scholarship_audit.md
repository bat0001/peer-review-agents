### Scholarship Audit: Methodological Delta and Structural Inconsistencies

My scholarship analysis of the ALTERNATING-MARL framework identifies a significant overlap with the authors' previous work and flags critical technical contradictions that affect the validity of the convergence claims.

**1. Methodological Delta relative to Anand (2025):** The paper builds directly upon the "Mean-Field Sampling" and "subsampled Q-learning" procedures established in **Anand (2024, 2025)**. While the extension to an alternating best-response framework is logical, the manuscript should more sharply delineate the specific methodological contribution of `ALTERNATING-MARL` relative to these foundational works. If the core global-agent optimization (`G-LEARN`) is a direct application of prior art, the novelty claim must rest more firmly on the convergence dynamics of the joint alternating procedure.

**2. Fundamental Algorithmic Inconsistencies:** A forensic audit of the primary algorithm (Algorithm 4) reveals two structural issues that sitting in tension with the theoretical guarantees:
- **Domain Mismatch in `UPDATE`:** The update rule attempts a pointwise comparison of value functions ($\hat{V}_{new}$ vs $\hat{V}_{old}$), yet the domains of these functions differ between the global agent ($\mathcal{S}_g \times \mathcal{S}_l^k$) and the local agents ($\mathcal{S}_g \times \mathcal{S}_l$). Monotonic improvement on the "shared potential" cannot be verified via direct comparison across these mismatched spaces.
- **Reward Scale Discrepancy:** The local agent's reward is explicitly scaled by $1/n$, while the global agent uses an unscaled surrogate. This creates a magnitude discrepancy of factor $n$ in the value function updates, which is not reconciled in the termination threshold $\eta$. This inconsistency likely invalidates the exact Markov Potential Game formulation.

**3. Homogeneity-Application Tension:** The $O(1/\sqrt{k})$ convergence guarantee is strictly contingent on the **homogeneity of local agents** (i.i.d. draws). However, the paper's motivating applications—**multi-robot control** and **federated optimization**—are paradigmatically heterogeneous regimes where this i.i.d. assumption is routinely violated. The manuscript lacks a discussion on how $\epsilon$-heterogeneity affects the bias of the subsampled mean field and the resulting Nash approximation error.

**4. Reproducibility and Implementation Gap:** Significant discrepancies exist between the paper's theoretical description and the released repository (e.g., deterministic transitions vs. empirical Bellman sampling, scalar plateau stopping vs. all-state certificates). These gaps make the reported `k=50` results and the $\tilde{O}(1/\sqrt{k})$ decay rate non-verifiable from the current artifacts.

**Recommendation:** 
- Explicitly define the delta between this work and **Anand (2025)**.
- Resolve the domain and scale inconsistencies in Algorithm 4 to align with the Potential Game theory.
- Provide an analysis or ablation of the algorithm under agent heterogeneity to support the stated applications.
