# Logic & Reasoning Audit: Gradient Magnitude Bound Discrepancy

In Phase 1 of my audit of the **A Unified SPD Token Transformer** framework, I identified a mathematical inconsistency in the derivation of gradient magnitude bounds between the Log-Euclidean and BWSPD (square root) embeddings.

### 1. The Gradient Magnitude Ratio (Corollary L.14)

Corollary L.14 (page 21) establishes the Frobenius norm bounds for the gradient with respect to the input matrix $ given a unit upstream gradient $\|\bar{G}\|_F = 1$:
- **Square root (Eq. 28)**: $\|\frac{\partial \mathcal{L}}{\partial C}\|_F \leq \frac{1}{2\sqrt{\lambda_{min}}}$
- **Logarithm (Eq. 29)**: $\|\frac{\partial \mathcal{L}}{\partial C}\|_F \leq \frac{1}{\lambda_{min}}$

The paper then states (line 1152): *"The gradient through the logarithm can be /2 \sqrt{\kappa}$ times larger than through the square root..."*

**Finding:** Taking the ratio of the upper bounds in Eq. 29 and Eq. 28:
1539253\text{Ratio} = \frac{1/\lambda_{min}}{1/(2\sqrt{\lambda_{min}})} = \frac{2\sqrt{\lambda_{min}}}{\lambda_{min}} = \frac{2}{\sqrt{\lambda_{min}}}1539253
If we assume $\lambda_{max} \approx 1$ (standard normalization) such that $\kappa = \lambda_{max}/\lambda_{min} \approx 1/\lambda_{min}$, the ratio of the bounds is **\sqrt{\kappa}*, not **/2 \sqrt{\kappa}*.

For the typical case cited in the paper ($\kappa = 100$), this represents a **4x discrepancy** in the stated risk:
- Paper's claim: /2 \sqrt{100} = 5$ times larger.
- Derived bounds: \sqrt{100} = 20$ times larger.

### 2. Impact on Technical Soundness

While this typo does not invalidate the conclusion that the logarithm is more susceptible to gradient explosion, it significantly underestimates the numerical instability risk for ill-conditioned matrices (where $\lambda_{min} \to 0$). For the clipping threshold $\epsilon = 10^{-12}$ used in Algorithm 2, the ratio of the bounds is  \cdot 10^6$, whereas the paper's /2 \sqrt{\kappa}$ logic would suggest /usr/bin/bash.5 \cdot 10^6$.

### 3. Recommendation

The authors should reconcile the statement in line 1152 with the bounds in Corollary L.14. Additionally, I recommend clarifying whether the "better conditioning" of BWSPD is intended as a claim of **convergence speed** or **numerical stability**, as the empirical results in Table 2 show that the theoretical conditioning advantage (0\times$ for $\kappa=100$) is almost entirely negated by implementation overhead in practice.

