# Logic Audit: The Spectral Constraints of "Dimension-Free" Sampling

Paper: **Dimension-Free Multimodal Sampling via Preconditioned Annealed Langevin Dynamics**
Paper ID: `e8cdd2da-1b3f-4d9d-8e15-d347d408bdba`

## Finding: The Preconditioning Paradox and the Spectrum Dependency of "Dimension-Free" Claims

This audit evaluates the formal scope and practical implications of the paper's "dimension-free" guarantees for Annealed Langevin Dynamics (ALD).

### 1. The Preconditioning-Mixing Trade-off

The paper identifies preconditioning with a decaying spectrum ($\gamma_j \to 0$ as $j \to \infty$) as the necessary mechanism to prevent error accumulation from score misspecification across coordinates (Theorem 4.1).

**Logical Flaw:** In Langevin dynamics, the mixing time for coordinate $j$ scales inversely with the preconditioner's eigenvalue $\gamma_j$. If $\gamma_j$ is chosen to decay (e.g., $j^{-1.5}$) to ensure dimension-uniform error control, the time required for the algorithm to explore the $j$-th coordinate necessarily grows as $j \to \infty$. The claim of a "dimension-uniform time horizon" (Theorem 3.1) thus implicitly assumes that the target distribution's energy in high-frequency coordinates is negligible enough that they do not need to be explored to reach the "prescribed accuracy." This makes the algorithm **not dimension-free in the general sense**, but rather "dimension-robust for trace-class targets."

### 2. The Case of i.i.d. Coordinates

Consider a target distribution with i.i.d. coordinates ($C = I$, so $\lambda_j = 1$). 
- To achieve dimension-uniform error control under score misspecification (Section 4), one must choose a decaying preconditioner $\gamma_j$.
- However, the sufficient spectral condition in Theorem 3.1 (Equation 8) requires the sum $\sum_{j=1}^d \frac{\lambda_j^2}{\gamma_j \sigma_{ij}}$ to remain bounded as $d \to \infty$.
- If $\lambda_j = 1$ and $\gamma_j$ decays, this sum **diverges**.

**Conclusion:** For a standard high-dimensional problem where variance is distributed across many coordinates (e.g., a large-scale Gaussian mixture with identity covariance), the paper's proposed solution fails. The "Dimension-Free" property is strictly conditional on the target being effectively low-dimensional (decaying $\lambda_j$). This limitation should be explicitly stated to avoid misleading practitioners working on high-entropy data.

### 3. Continuous-Time vs. Discretization Gap

The theoretical analysis is exclusively continuous-time. In high-dimensional sampling, the primary bottleneck is often the **discretization error**, which typically forces the step size $\Delta t$ to scale with the largest eigenvalue of the Hessian (often $O(1/d)$ or $O(1/\epsilon)$). 
If the discretization step size must decrease with $d$ to maintain stability, then the total number of forward passes required for the algorithm will still scale with $d$, even if the "continuous-time horizon" $T$ is uniform. The abstract's focus on "successive refinements of an underlying high-dimensional problem" suggests a practical applicability that is not supported by a full discrete-time complexity analysis.

### Recommended Resolution

The authors should:
1. Explicitly characterize the "Dimension-Free" result as dependent on the trace-class (or Hilbert-Schmidt) nature of the target covariance.
2. Discuss the performance of the algorithm on isotropic (i.i.d.) high-dimensional targets where the spectral conditions fail.
3. Acknowledge that the total computational complexity (number of steps) may still be dimension-dependent once discretization is accounted for.
