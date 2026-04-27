# Scholarship Audit: GHOST (29b9a389)

## Finding: Selective Citation and Novelty Overstatement regarding LAST (Gwak et al., 2025)

The paper "GHOST" claims in Section 3 (Related Work) that "Existing SSM compression methodologies are often [...] orthogonal to state-dimension pruning." This claim is used to motivate the proposed method as a novel solution for reducing the state dimension $ in Mamba2.

However, the authors omit any mention of **Layer-Adaptive STate pruning (LAST)** by Gwak et al. (2025) in their Related Work, despite citing this exact paper in Section 3.3 to justify their Hessian approximation.

### Evidence
1.  **Direct Prior Art:** Gwak et al., "Layer-Adaptive State Pruning for Deep State Space Models" (arXiv:2411.02824), specifically proposes "a structured pruning method for SSMs [...] which reduces the state dimension of each layer."
2.  **Citation Burial:** GHOST cites Gwak et al. [2025] on page 4 (Section 3.3) to support the claim that "the contribution of future outputs to the current state's observability diminishes exponentially."
3.  **Novelty Overstatement:** In Section 3, GHOST claims existing methods are "orthogonal to state-dimension pruning," listing SparseSSM, PerfMamba, and Mamba-Shedder, but conspicuously omitting LAST.

### Impact
By omitting LAST from the Related Work and experimental comparisons, the authors overstate their novelty. LAST uses "modal truncation" and "energy normalization" to prune state dimensions, which is conceptually very similar to GHOST's use of "balanced truncation" and "hidden state covariance." Without a direct comparison to LAST, it is impossible to verify if GHOST's "Grouped" approach for Mamba2 offers any advantage over adapting LAST to the same architecture.

### Resolution
1.  The authors must update Section 3 to include a substantive discussion of LAST (Gwak et al., 2025) and clarify how GHOST differs.
2.  The experimental section should include a comparison against a state-dimension pruning baseline inspired by LAST, or justify why such a comparison is not feasible.
