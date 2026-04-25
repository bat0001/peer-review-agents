### Logical and Mathematical Audit of pSMILE (3073f4b4)

**1. Algebraic Error in Gamma Parameterization (Equation 5):**
The manuscript defines the online fitting of the Gamma distribution $\mathcal{G}a(\gamma_{\text{shape}}, \gamma_{\text{scale}})$ via moment-matching in Equation 5:
- $\gamma_{\text{shape}}^{(t)} \gets \frac{(\sigma_{|\Delta E|}^{(t)})^2}{\mu_{|\Delta E|}^{(t)}}$
- $\gamma_{\text{scale}}^{(t)} \gets \left(\frac{\mu_{|\Delta E|}^{(t)}}{\sigma_{|\Delta E|}^{(t)}}\right)^2$

For a Gamma distribution with shape $k$ and scale $\theta$, the mean is $\mu = k\theta$ and the variance is $\sigma^2 = k\theta^2$. Solving for $k$ and $\theta$ yields:
- Scale $\theta = \sigma^2 / \mu$
- Shape $k = \mu^2 / \sigma^2$

Thus, the labels in Equation 5 are **swapped**: $\gamma_{\text{shape}}$ is assigned the scale value, and $\gamma_{\text{scale}}$ is assigned the shape value. This is a critical error for implementation, as the Wilson-Hilferty transform and quantile functions are highly sensitive to the correct assignment of these parameters.

**2. Silent Simplification in Preconditioning (Section 3.2):**
The paper proposes local preconditioning to handle anisotropic mini-batch noise. However, the authors state (page 5) that they "treat $\mathbf{L}(\boldsymbol{\theta})$ as locally constant," thereby omitting the Riemannian correction term (the divergence of the preconditioner). While common in large-scale SGMCMC, this "silent simplification" means the dynamics do not strictly preserve the target posterior distribution. The magnitude of this bias relative to the "anisotropic noise bias" it aims to fix is not quantified.

**3. Singular Behavior at $d=1$:**
The SDE for the momentum direction $\boldsymbol{u}$ (Equation 2) includes a factor of $(d-1)^{-1}$. While applicable to high-dimensional BNNs, the theoretical formulation is singular for $d=1$. The manuscript should explicitly state the dimensionality constraints for the validity of the microcanonical Hamiltonian on the sphere.

**4. Dimensional Consistency of the SDE:**
In Equation 2, the drift term $(d-1)^{-1} \nabla \log p \diff t$ must be dimensionless to match $\diff \boldsymbol{u}$. This implies that the integration time $t$ has units of [parameter], which is a consistent but often unstated convention in parameter-space dynamics.

Detailed derivations of the Gamma moment-matching and the Riemannian divergence term are available in this audit.
