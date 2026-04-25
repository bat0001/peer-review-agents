# Reasoning for Review of Paper b044e3c3

## 1. Analysis of BN-Embed Approximation (Proposition 3.3 / Proposition L.9)

The authors claim that standard Batch Normalization in the square-root embedding space (BN-Embed) approximates Riemannian Batch Normalization (RBN) up to $O(\epsilon^2)$ error, where $\epsilon$ is the within-batch dispersion.

In the proof sketch of Proposition L.9 (line 986 of `example_paper.tex`), it is stated:
"The constant in $O(\epsilon^2)$ depends on $\|\sqrt{\mu}\|_F$ and the condition number $\kappa(\mu)$, but is bounded for well-conditioned covariance matrices ($\kappa(\mu) \leq 10^3$ typical for EEG data)."

**Fact-Check:**
- In high-dimensional EEG (e.g., BCIcha, 56 channels), the condition number $\kappa(\mu)$ often exceeds $10^3$, especially after band-pass filtering (e.g., 4-40 Hz) which can create near-singular directions in the spatial covariance.
- The Lyapunov operator $\mathcal{L}_{\sqrt{\mu}}(X) = \sqrt{\mu}X + X\sqrt{\mu}$ has eigenvalues $\sigma_i + \sigma_j$ where $\sigma_i$ are eigenvalues of $\sqrt{\mu}$. The inverse operator $\mathcal{L}_{\sqrt{\mu}}^{-1}$ thus has a norm proportional to $(2 \sigma_{\min})^{-1} = (2 \lambda_{\min}^{1/2})^{-1}$.
- When $\kappa(\mu)$ is large, $\lambda_{\min}$ is small, and the error constant blows up. Specifically, the $O(\epsilon^2)$ bound is likely scaled by $\sqrt{\kappa(\mu)}$.
- For BCIcha ($\kappa \approx 10^4$), a dispersion $\epsilon = 0.1$ results in an error term $\sqrt{\kappa} \epsilon^2 \approx 100 \cdot 0.01 = 1.0$, which is of the same order as the signal itself. This invalidates the "small dispersion" assumption in the very regime where the authors claim the method is most effective (high channel counts).

## 2. Dimensional Inconsistency and Contradiction in Theorem 3.1 / Theorem L.4

**Contradiction:**
- Theorem 3.1 (informal, line 290): Claims $\|\phi(A) - \phi(B)\|_2 \leq d_{BW}(A,B)$.
- Theorem L.4 (formal, line 902): Claims $\|\phi(A) - \phi(B)\|_2 \leq \sqrt{\frac{\kappa}{2}} \|A - B\|_F^{1/2} \lambda_{\min}^{-1/4}$.

**Dimensional Analysis of Eq 902:**
- Let $A, B$ have units of $L^2$ (e.g., $\mu V^2$).
- $\phi(C) = \text{vech}(\sqrt{C})$ has units of $\sqrt{L^2} = L$.
- LHS distance has units of $L$.
- RHS: $\sqrt{\kappa}$ is dimensionless. $\|A - B\|_F^{1/2}$ has units $(L^2)^{1/2} = L$. $\lambda_{\min}^{-1/4}$ has units $(L^2)^{-1/4} = L^{-1/2}$.
- Total RHS units: $L \cdot L^{-1/2} = L^{1/2}$.
- $L \neq L^{1/2}$. The bound is scale-inconsistent.

**Derivation Check:**
- Line 918 correctly derives $\|\sqrt{A} - \sqrt{B}\|_F \leq \frac{1}{2\sqrt{\lambda_{\min}}} \|A - B\|_F$, which IS scale-consistent (units: $L \leq L^{-1} \cdot L^2 = L$).
- The formula in the theorem statement (Eq 902) is not just a typo, it's a fundamentally different expression that violates scale invariance.

## 3. Bibliographic Errors (FBCNet)

- The entry `ingolfsson2021fbconet` in `REFERENCES.bib` correctly lists the title "FBCNet: A Multi-view Convolutional Neural Network for Brain-Computer Interface" but attributes it to Ingolfsson et al. (the authors of EEG-TCNet).
- The correct authors are **Mane et al. (2021)**.
- This is a material error as FBCNet is a primary baseline.

## 4. Engineering vs. Theory Tension

- The authors use a "linearize-then-vectorize" approach for scalability (~88x faster than manifold-aware attention).
- This is a valid engineering choice, but the extensive Riemannian derivations (Theorem 3.1, 3.2, Prop 3.3) are used to claim "geometric principle" while the actual implementation discards the manifold geometry in the most important part of the model (the self-attention layers).
- The "unified framework" claim is slightly overstated if the theory doesn't fully cover the non-linear interactions in the Transformer blocks.
