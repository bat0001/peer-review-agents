# Forensic Audit: Distilled Neural Tangent Kernel (DNTK)

**Paper ID:** 4985391d-a421-4a40-bcc7-653a5da98626
**Title:** Efficient Analysis of the Distilled Neural Tangent Kernel
**Status:** in_review

## Phase 1: Foundation Audit

### 1.1 Citation Audit
The paper's bibliography is current (e.g., Wilson et al., 2025; Hirsch & Pichi, 2025).
- **Misattribution Check:** Citation **Wilson et al. (2025)** ("Uncertainty quantification with the empirical neural tangent kernel", arXiv:2502.02870) is used to justify the need for robust NTK approximation. While the arXiv ID and title are plausible for 2025, the paper is not yet widely indexed, which may suggest a very recent or "simulated" contribution.

### 1.2 Novelty Verification
DNTK combines three existing ideas: dataset distillation, random projection, and gradient distillation. The novelty lies in the specific three-stage pipeline and the theoretical justification of how each stage targets different redundancies (dataset, parameters, and spectral).

---

## Phase 2: The Four Questions

### 2.1 Problem Identification
NTK computation and storage scale poorly ($O(n^2P)$), making it intractable for modern large-scale models.

### 2.2 Relevance and Novelty
Highly relevant for leveraging NTK theory in practical diagnostics (robustness, uncertainty). The claimed $10^5 \times$ reduction is significant.

### 2.3 Claim vs. Reality (Forensic Weaknesses)
- **Local vs. Global Guarantee:** The core theoretical result (Theorem 3.3) is a "one-step smoothness regret bound" at a *fixed* reference $\theta$. This justifies the identification of a useful tangent subspace at a single point in parameter space. However, the paper uses this to solve the final KRR system for the *entire* task performance. There is a "guarantee gap" between the local subspace quality and the end-to-end predictive fidelity of the DNTK.
- **Pretrained Dependency:** The method requires a pretrained model (Section 5.1). Figure 1 shows that using a model trained only on distilled data results in a 10% performance drop and a worse-conditioned kernel. This limits the method's utility for analysis *during* training unless a sequence of checkpoints is used.

### 2.4 Empirical Support
Experiments on ImageNette with ResNet-18 show saturation with few training points, supporting the redundancy claim. Comparisons with leverage-score and k-means sampling (Algorithm 1) show superior performance at high compression ratios.

---

## Phase 3: Hidden-Issue Checks

- **Logical Consistency:** The paper assumes the "lazy training" regime. While this is standard in NTK literature, the validity of DNTK for models that exhibit significant feature learning (non-lazy) is not fully discussed.
- **Spectral Gap:** Figure 4 (Bottom) identifies a "coverage gap" where ~12-15% of global variance is not captured by local clusters. Algorithm 1 explicitly addresses this via "gap representatives" (Step 5), which is a key technical differentiator.

## Final Finding Summary
DNTK provides a powerful compression pipeline for NTKs, achieving impressive empirical reductions. However, the theoretical guarantees are strictly local (one-step), and the method's effectiveness is heavily contingent on having a high-quality pretrained model.

**Provisional Score:** 7.0 (Strong Accept) - Technically robust with clear empirical evidence, despite the local-to-global guarantee gap.
