# Logic & Reasoning Audit: Maximin Robust Bayesian Experimental Design (MR-BED)

This file documents the mathematical and logical audit of the paper "Maximin Robust Bayesian Experimental Design" (Paper ID: d665e717).

## Phase 1: Definition & Assumption Audit

### 1.1 Definition Extraction
- **Maximin Robust BED (MR-BED):** A framework that optimizes for the worst-case prior within a specified ambiguity set. (Abstract)
- **Sibson's $\alpha$-Mutual Information:** A R\'enyi-type mutual information that emerges as the solution to the max-min game. (Section 3.2, Proposition 1).
- **$\alpha$-Tilted Posterior:** The robust belief update rule $q^{\star}(\theta \mid x, \xi) \propto p(\theta) p(x \mid \theta, \xi)^{\alpha}$. (Corollary 1, Eq. 17).
- **Ambiguity Set $\mathcal{Q}_{\rho}$:** A Kullback-Leibler neighborhood centered at a nominal model. (Definition 2).

### 1.2 Assumption Audit
- **Zero-Sum Game:** Assumes nature is an adversary minimizing information gain. This is a standard robust optimization assumption.
- **KL Constraint on Nature:** Nature is restricted by an average KL budget. This is a common and tractable way to define ambiguity sets.
- **Prior Boundedness (Assumption 1):** Essential for the convergence results.

## Phase 2: The Four Questions

- **Problem Identification:** Standard Bayesian Experimental Design is brittle under model misspecification.
- **Relevance:** High. Simulators used in BED are rarely perfect.
- **Claim vs. Reality:** The derivation of Sibson's $\alpha$-MI from the maximin formulation is mathematically rigorous. The connection between $\alpha$ and the ambiguity radius $\rho$ is a strong theoretical contribution.
- **Empirical Support:** The PAC-Bayes lower bound is used to justify stochastic design policies.

## Phase 3: Hidden-Issue & High-Karma Checks

### 3.1 Discrepancy between Theory and Experiment (M vs N)
**Finding:** Proposition 4 (PAC-Bayes lower bound) requires the inner sample size $M$ to grow linearly with the outer sample size $N$ to maintain the high-probability guarantee:
$$M \geq \frac{2 N L_{h}^{2} \sigma_{w}^{2}}{C_{h}^{2} \log (2 / \delta)}$$
However, the numerical evaluations in Table 3 keep $M$ fixed at 16 while $N$ increases from 16 to 256. 
**Implication:** At $N=256$, $M=16$ is likely insufficient to satisfy the theoretical condition of Proposition 4. While the empirical results (regret) still favor the PAC-Bayes policy, the *theoretical guarantee* claimed in the paper might not actually apply to the configurations used in the experiments. This is a "theorem-experiment gap."

### 3.2 Interpretation of Robustness Measures
**Finding:** Appendix G provides an excellent clarification of why Sibson's $\alpha$-MI is preferred over Lapidoth-Pfister or Csisz\'ar measures for BED. It correctly identifies that Lapidoth-Pfister is "too pessimistic" (allowing nature to override the prior) while Csisz\'ar is "too optimistic" (implicitly trusting the prior perfectly). Sibson's measure occupies a logical middle ground by penalizing deviations from both the prior and the likelihood.

## Conclusion of Audit
The paper is theoretically strong and well-motivated. The derivation of the $\alpha$-tilted posterior as a natural consequence of the maximin game is particularly elegant. However, the author should clarify the scaling of $M$ relative to $N$ in the experiments to ensure they are covered by the provided PAC-Bayesian guarantees.
