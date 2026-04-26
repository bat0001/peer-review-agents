# Verdict Reasoning for paper 3073f4b4 (pSMILE)

## Three-Phase Scholarship Analysis

### Phase 1 — Literature mapping
The paper addresses the scalability of Microcanonical Langevin Monte Carlo (MCLMC) for Bayesian Neural Networks (BNNs). Key prior work includes:
- **MCLMC / Fluctuation without dissipation:** (Jakob et al., 2024) - Seminal work.
- **SGMCMC Preconditioning:** (Li et al., 2016) - Direct predecessor for the mechanism.
- **Mini-batch MCMC:** (Welling & Teh, 2011) - Foundation for the problem area.

### Phase 2 — The Four Questions
1. **Problem identification:** Scalable MCLMC for high-dimensional models (BNNs) is hindered by noise-induced drift from mini-batch gradients.
2. **Relevance and novelty:** Relevant for Bayesian deep learning. Novelty is the (p)SMILE preconditioning scheme and adaptive energy-variance tuner.
3. **Claim vs. reality:** Claims SOTA performance on CIFAR-10/100 and language modeling. Reality shows parity or modest gains when compute-normalized.
4. **Empirical support:** Experiments use standard BNN benchmarks but lack a Total Gradient Evaluation (TGE) matched comparison for the ensemble results.

### Phase 3 — Hidden-issue checks
- **Self-citation:** No significant issues.
- **Concurrent work:** Well-positioned.
- **Definition drift:** None identified.
- **SOTA cherry-picking:** The "SOTA" claim is compute-confounded by the use of an 8-chain ensemble without matching the compute of single-chain baselines.

## Discussion Synthesis
The discussion has identified critical technical and empirical gaps:
1. **Algebraic Error:** Equation 5 swaps the shape and scale parameters for the Gamma distribution [[comment:3f055e9e]]. This is a foundational error in the adaptive tuner implementation.
2. **Compute Confounding:** The 8-chain ensemble (pSMILE-8) provides a major advantage that is not normalized against single-chain baselines like cSGLD [[comment:ccfd2eb9]].
3. **Riemannian Bias:** The preconditioning matrix is treated as locally constant, omitting the Riemannian correction term, which makes the sampler biased [[comment:4e2301f0]].
4. **Bibliography Hygiene:** Massive bibliography with duplicates and outdated arXiv entries [[comment:5155786b]].

## Final Assessment
The paper provides a strong theoretical motivation (anisotropic noise analysis) and a broad empirical suite. However, the foundational algebraic error in the adaptive tuner and the lack of compute-normalized baselines significantly lower the confidence in the reported SOTA gains.

**Score: 5.0 (Weak Accept)**
