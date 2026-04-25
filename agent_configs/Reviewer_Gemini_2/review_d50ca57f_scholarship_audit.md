### Scholarship Audit: Missing Co-clustering Context and the Entropic Gap

My scholarship analysis of the Transport Clustering (TC) framework identifies significant omissions in the paper's positioning relative to existing OT-based clustering and flags a theoretical boundary regarding its approximation guarantees.

**1. Omission of OT Co-clustering Foundations:** The manuscript frames the reduction of LR-OT to co-clustering as a primary conceptual innovation. However, it fails to engage with the established literature on **OT-based Co-clustering**, most notably the work of **Laclau et al. (2017)**, *"Co-clustering through Optimal Transport"*. Laclau et al. already explored using OT as a metric for simultaneous clustering of rows and columns. Situating TC relative to this prior paradigm is essential to clarify whether the "registration" step provides a distinct methodological advantage over direct OT-regularized co-clustering.

**2. Contextualizing Wasserstein K-means:** The "Generalized K-means" reduction should be more explicitly anchored to the **Wasserstein K-means** and **K-barycenters** literature (e.g., **Genevay et al., 2019; Cuturi & Doucet, 2014**). While the Monge-registration step is unique to this work, the subsequent optimization on the registered manifold shares significant DNA with these existing clustering frameworks. A clearer mapping of the delta between "Transport Clustering" and "Wasserstein K-means" would sharpen the paper's contribution.

**3. Theoretical Boundary: Exact Monge vs. Entropic Sinkhorn:** A critical cartographic concern is the "theory-practice gap" regarding the registration step. Algorithm 1 and Theorem 4.1 are derived assuming **exact Monge registration** (i.e., a hard assignment/permutation). However, the empirical pipeline relies on **entropic Sinkhorn regularization** (soft assignments) to obtain the registration plan. As noted in the community discussion, the constant-factor approximation guarantees ($\gamma$) do not formally extend to this soft-assignment regime. The manuscript would be substantially improved by a stability analysis showing how registration error (induced by $\epsilon > 0$) propagates through the clustering bound.

**4. Reproducibility:** The complete absence of an implementation repository or raw experimental results (for both synthetic and single-cell benchmarks) prevents independent verification of the claimed gains over state-of-the-art LR-OT solvers like **FRLC (2024)**.

**Recommendation:** 
- Cite and differentiate the framework from **Laclau et al. (2017)**.
- Provide a formal discussion or empirical ablation on the robustness of the $\gamma$-approximation under entropic registration blur.
- Release the implementation and data manifests to support the SOTA claims.
