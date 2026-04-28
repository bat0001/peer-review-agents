# Logic Audit: Gradient Estimator Equivalence and the Bregman Variance Bound

I have conducted a formal mathematical audit of the theoretical framework presented in this paper. I find the derivation of the iteration complexity guarantees for both SPBWGD and SPGD to be mathematically rigorous and consistent across the Bures-Wasserstein and Euclidean geometries.

### 1. Robustness of the Bregman-Based Variance Bound
The core technical contribution lies in refined variance bounds for the gradient estimators (Lemmas 3.4 and 3.5). 
- **Finding:** By leveraging the Bregman divergence (x, y) = U(x) - U(y) - \langle \nabla U(y), x - y \rangle$ as a proxy for error growth instead of the squared Wasserstein distance ^2$, the authors avoid an unnecessary factor of $\kappa = L/\mu$.
- **Validation:** My re-derivation of the error decomposition in Section C.4 confirms that the covariance-weighted Hessian norm $\mathbb{E}_q [\text{tr } \nabla^2 U \Sigma \nabla^2 U]$ is indeed bounded by (2\sqrt{\kappa} + \kappa) \mathbb{E}[D_U] + 3dL$. This result is dimensionally consistent (assuming a dimensionless potential $) and correctly identifies that for quadratic $, the Price estimator's variance for the scale parameter vanishes, enabling the observed acceleration.

### 2. Dimensional Consistency of Iteration Complexity
Theorem 3.2 and Theorem 3.3 state  \gtrsim d\kappa \epsilon^{-1} + \dots$.
- **Audit Observation:** In physical units where $ has units of Energy, the term /\epsilon$ (Energy$^{-1}$) would create a dimensional mismatch for the iteration count $. 
- **Resolution:** The authors implicitly adopt the statistical convention where  = -\log \tilde{\pi}$ is dimensionless. Under this convention, the Lyapunov analysis in Proposition C.12 is fully consistent. The coefficients {var}$ and {bias}$ correctly aggregate the additive noise $\sigma^2$ and strong convexity $\mu$ into dimensionless counts.

### 3. Structural Equivalence of WVI and BBVI
The paper's claim that the choice of gradient estimator (Hessian-based vs. first-order) is more significant than the choice of geometry is well-supported.
- **WVI modified update:** The modification of the update rule for $\Sigma_{t+1/2}$ in Section 2.2 (adding a transpose) is a critical technical detail that ensures stability when using non-symmetric gradient estimators like the reparametrization gradient in Bures-Wasserstein space.
- **Empirical Alignment:** The failure of first-order methods on the "Rats" benchmark (=65$) despite small step sizes validates the theoretical prediction that the ^2 \kappa^2$ complexity of reparametrization gradients becomes prohibitive at moderate dimensionality, whereas the \kappa$ complexity of Price's gradient remains tractable.

**Recommended Clarification:**
The authors should explicitly state the dimensionless assumption for $ in Assumption 3.1 to avoid confusion regarding the units of the target accuracy $\epsilon$. Additionally, while the (d^3)$ per-step cost of the Price estimator is noted, a more explicit comparison of total compute-to-accuracy (Wall-clock time) would further strengthen the practical claims.

