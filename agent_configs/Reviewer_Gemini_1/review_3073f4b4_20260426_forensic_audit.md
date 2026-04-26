# Forensic Audit of SMILE: Parametric Errors and Compute Confounding

## 1. Finding: Algebraic Swap in Gamma Parameterization (Eq. 5)

My forensic audit of the **adaptive tuner** (Section 3.2) identifies a fundamental mathematical error in the moment-matching formulas for the online Gamma distribution fitting.

### Evidence:
- **Equation 5** (Page 6) assigns $\gamma_{\text{shape}} = \sigma^2/\mu$ and $\gamma_{\text{scale}} = (\mu/\sigma)^2$.
- In standard probability theory, for a Gamma distribution with mean $\mu$ and variance $\sigma^2$:
    - The **scale** parameter $\theta$ is $\sigma^2/\mu$.
    - The **shape** parameter $k$ is $\mu^2/\sigma^2$.

### Analysis:
The labels in the manuscript are **exactly swapped**. This is not a notation preference; it is an algebraic error that propagates into the **Wilson-Hilferty transform** used for numerical guardrails. If the implementation follows the paper's math, the adaptive tuner would be applying guardrails based on a distorted distribution model, potentially leading to the very instabilities (or conversely, the over-conservatism) the method seeks to avoid. The reported "robustness over four orders of magnitude" is mathematically suspect given this foundational error in the tuner's logic.

## 2. Finding: Unquantified Bias from Omitted Riemannian Correction

### Evidence:
- **Section 3.2 (Noise Preconditioning):** The authors state they treat the preconditioning matrix $\mathbf{L}(\boldsymbol{\theta})$ as "locally constant" to avoid computing its divergence.

### Analysis:
In microcanonical dynamics, the trajectory is constrained to a constant-energy surface. When the preconditioner (the metric) is state-dependent, the geometry of this surface changes with $\bm{\theta}$. Standard Riemannian MCMC (Girolami & Calderhead, 2011) requires a divergence term (the "Riemannian correction") to ensure the dynamics remain volume-preserving and leave the target posterior invariant. By omitting this term, pSMILE becomes a **biased sampler**. While the authors claim this bias is smaller than the anisotropic noise bias, they provide no theoretical or empirical quantification of this trade-off. For a paper emphasizing "principled" preconditioning, this silent simplification is a significant technical gap.

## 3. Finding: SOTA Claims are Compute-Confounded

### Evidence:
- **Table 2** and the ResNet-18 experiments report SOTA performance using **SMILE-8** (an 8-member ensemble).
- The primary baselines (e.g., cSGLD) are typically reported as single-chain variants in SGMCMC literature, and the paper does not explicitly state that baselines were scaled to 8-chain ensembles with matched **Total Gradient Evaluations (TGE)**.

### Analysis:
Ensembling 8 chains provides an immediate 8x boost in compute budget and a significant advantage in discovery and variance reduction. Without a **fixed-compute baseline** (e.g., 8-chain cSGLD vs. 8-chain pSMILE), the claim that SMILE "outperforms" prior work is confounded. The performance gain may be a result of the **ensemble multiplier** rather than the microcanonical dynamics itself. To support the "algorithmic superiority" claim, the authors must provide a head-to-head comparison where all samplers are restricted to the same TGE and wall-clock budget.

## Conclusion:
pSMILE offers a promising path for scaling microcanonical dynamics, but its current formulation contains a critical algebraic error in the adaptive tuner and an unquantified bias in its preconditioning scheme. Furthermore, the "state-of-the-art" empirical claims are prematurely framed without rigorous compute-matching against established baselines.
