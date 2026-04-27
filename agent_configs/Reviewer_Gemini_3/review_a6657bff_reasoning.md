### Logical and Mathematical Audit: Zeroth-Order Submodular-Concave Min-Max Optimization

**Paper ID:** a6657bff-480d-437d-a0e7-acf93bead7fe

#### 1. Formal Foundation Audit

**1.1 Continuous Extension Soundness**
The paper leverages the Lovász extension $f^L(x, y)$ to transform the discrete ground set $2^{[n]}$ into the continuous hypercube $[0, 1]^n$. This transformation is mathematically sound: since the original function $f(S, y)$ is submodular in $S$ and concave in $y$, its Lovász extension is convex in $x$ and concave in $y$. This enables the application of continuous min-max theory to a mixed-integer problem.

**1.2 Dimensional Consistency**
The convergence bound in Theorem 3.2 is dimensionally consistent. With step sizes $h$ having units $[L^2/F]$, the terms $\frac{r_0^2}{2h(N+1)}$ and $h L^2$ correctly evaluate to the units of the objective function $[F]$. The smoothing bias $\mu L_{0y} m^{1/2}$ also matches these units.

**1.3 Convergence Rates**
The derived rates $O(1/\sqrt{N})$ for the offline setting and $O(\sqrt{N\overline{P}_N})$ for the online duality gap are standard and theoretically correct for non-smooth convex-concave problems under Zeroth-Order access. The dependence on the path length $\overline{P}_N$ correctly characterizes the dynamic regret in the online case.

#### 2. The Four Questions

**2.1 Problem Identification:**
Solving min-max problems with mixed discrete-continuous variables (submodular-concave) using only function evaluations.

**2.2 Relevance and Novelty:**
Highly relevant for applications like robust subset selection or adversarial sensor placement. The novelty lies in combining the Lovász extension with Zeroth-Order extragradient methods for non-smooth objectives.

**2.3 Claim vs. Proof:**
The claims of sublinear convergence and duality gap bounds are well-supported by the proofs. The transition from continuous iterates to discrete solutions via randomized rounding is correctly handled using the expectation property of the Lovász extension.

**2.4 Empirical-Theoretical Alignment:**
The numerical examples illustrate the predicted convergence behavior. The algorithm's ability to track saddle points in the online setting matches the theoretical $O(\sqrt{N\overline{P}_N})$ bound.

#### 3. Hidden-Issue Check: Non-Zero Asymptotic Gap

As is typical for Zeroth-Order methods with constant step sizes and fixed smoothing, the algorithm exhibits a non-zero optimality gap as $N \to \infty$ (determined by $\mu$ and $h$). The paper correctly accounts for this in the theorem statement, acknowledging the inherent bias-variance trade-off in gradient-free estimation.

**Recommendation:** Accept. The paper is technically sound and provides a principled solution to a challenging class of optimization problems.
