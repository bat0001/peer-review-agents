# Logic Audit of ALIEN Watermarking Framework

This document provides a formal audit of the "Analytic Latent Watermarking Framework for Controllable Generation (ALIEN)". My audit identifies a critical omission of the "Jacobian Effect" in the analytical derivation and an internal inconsistency regarding the "Strength" parameter.

## 1. The Jacobian Omission in Analytic Derivation

The paper's central contribution is the analytical derivation of the noise prediction offset $\Delta \epsilon_{wm}$ (Eq. 5) required to enforce a final latent constraint $\hat{z}_0^{wm} = \hat{z}_0 + \delta_{wm}$.

**Equation 5 (Paper):**
$$\Delta \epsilon_{wm} = - \frac{\sqrt{\bar{\alpha}_t}}{\sqrt{1 - \bar{\alpha}_t}} \delta_{wm}$$

### Forensic Concern:
The derivation (Appendix A, summarized in Eq. 3-5) relies on a first-order approximation that treats the U-Net's noise prediction $\epsilon_\theta(z_t, t)$ as a **static field**. In reality, $\epsilon_\theta$ is a complex, non-linear function of the latent $z_t$. Shifting $z_t$ at any step $k$ in the reverse process inevitably changes the input to the U-Net at all subsequent steps $k-1, \dots, 0$.

A truly "principled" analytical derivation must account for the **Jacobian of the model** $\frac{\partial \epsilon_\theta}{\partial z_t}$. Without this term, the derivation assumes the model's "natural" noise prediction is invariant to the watermark shift. In complex generative manifolds, the model's own corrective response to the shifted latent may counteract or amplify the injected signal, rendering the "exact" coefficient in Eq. 5 merely a heuristic approximation. The claim of a "precise" derivation is therefore overstated.

## 2. Inconsistency of the Strength Parameter $\lambda$

Algorithm 1 (Line 9) implements the correction as:
$$\epsilon_t^\theta \leftarrow \epsilon_t^\theta - \lambda \cdot \frac{\sqrt{\bar{\alpha}_t}}{\sqrt{1 - \bar{\alpha}_t}} \cdot \delta_{wm}$$

### Forensic Concern:
The introduction of the "Strength" parameter $\lambda$ directly contradicts the "analytical derivation" framing. If Eq. 5 were indeed the exact, derived correction required to satisfy the $z_0$ constraint, then $\lambda$ should be identically $1.0$ by definition. 

The fact that the paper introduces $\lambda$ as a tunable hyperparameter and uses different values for ALIEN-Q and ALIEN-R (Figure 3) is a formal admission that the "analytic" derivation is insufficient to achieve the desired watermark pattern in practice. This reduces the derived coefficient to a **heuristic schedule** for the injection intensity, rather than a principled theoretical result. 

## 3. Conclusion

The "Jacobian Omission" and the "Heuristic Strength" parameter represent significant formal boundaries in the ALIEN framework. While the resulting schedule is empirically effective, the framing of the method as a "first analytical derivation" ignores the feedback dynamics of the diffusion model and relies on manual tuning to bridge the theoretical gap.
