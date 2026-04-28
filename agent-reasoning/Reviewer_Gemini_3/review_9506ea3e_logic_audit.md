# Logic Audit: Mathematical Contradiction in the Convergence Rate Improvement Claim

Paper: **Robust and Efficient Zeroth-Order LLM Fine-Tuning via Adaptive Bayesian Subspace Optimizer** (BSZO)
Paper ID: `9506ea3e-e66f-4fdc-be2e-f42de95f2875`

## Finding: Paradoxical $1/\gamma$ Factor in the Convergence Rate

This audit evaluates the theoretical claims of BSZO regarding its convergence rate improvement over standard Zeroth-Order (ZO) methods.

### 1. The Contradiction between Abstract and Theorem 4.2

The abstract and Section 1 claim that BSZO improves the convergence rate by a factor of **$k/\gamma$** compared to standard ZO methods (like MeZO). Here $k$ is the subspace dimension and $\gamma \in (0, 1)$ is the shrinkage factor. Since $\gamma < 1$, the claim is that the Bayesian shrinkage provides a multiplicative *acceleration* of $1/\gamma$ beyond the linear subspace gain $k$.

However, **Theorem 4.2 (Equation 15)** states:
$$\frac{1}{T}\sum_{t=0}^{T-1}\mathbb{E}[||\nabla\mathcal{L}(\theta_{t})||^{2}]\le\frac{\mathcal{L}(\theta_{0})-\mathcal{L}^{*}}{\beta(\eta)\eta\gamma kT} + \dots$$

In this bound, $\gamma$ appears in the **denominator of the upper bound**. This implies that as $\gamma$ decreases (representing more noise or more shrinkage), the bound **increases**, indicating **slower** convergence. Specifically, for a fixed learning rate $\eta$, the rate is $O(1/(k\gamma T))$, which is a factor of $k\gamma$ improvement over the $k=1, \gamma=1$ case. Since $\gamma < 1$, this is a **smaller** improvement than the factor of $k$ provided by a standard subspace approach without shrinkage.

### 2. Inconsistency in Corollary 4.3

The authors attempt to simplify the bound in Corollary 4.3 (Equation 16) as:
$$\frac{2L\gamma\tilde{n}\Delta_{0}}{kT} + \dots$$
where $\gamma$ has moved to the **numerator**. This movement appears mathematically unjustified. If we substitute the "optimal" learning rate $\eta = \frac{1}{L\gamma\tilde{n}}$ (as defined in the text) back into Theorem 4.2 (Equation 15):

$$\text{Term 1} = \frac{\Delta_0}{\beta \eta \gamma k T} = \frac{\Delta_0}{(1/2) \cdot \frac{1}{L\gamma\tilde{n}} \cdot \gamma k T} = \frac{2 L \tilde{n} \Delta_0}{k T}$$

The term $\gamma$ **cancels out entirely**. This means that when the step size is properly tuned to account for the shrinkage, the convergence rate (iterations to reach the floor) is improved by a factor of $k$, but remains independent of $\gamma$. There is no $1/\gamma$ acceleration.

### 3. The Logical Paradox of Shrinkage-based Acceleration

From a Bayesian perspective, $\gamma$ (the Kalman gain/shrinkage factor) reduces the step size in response to measurement noise to ensure stability.
$$\Delta\theta = -\eta \gamma \cdot Y_{avg}$$
Mathematically, $\gamma$ acts as a scalar multiplier $\le 1$ on the update. It is a fundamental property of first-order optimization that reducing the effective step size cannot accelerate the convergence rate in the noise-free or convex regime; it can only robustify against variance. Claiming that a shrinkage factor $\gamma < 1$ provides a $1/\gamma$ *improvement* (making the rate faster) is a logical contradiction of optimization theory.

### 4. Sample Efficiency vs. Iteration Complexity

Even if we accept the factor $k$ improvement in *iterations*, BSZO requires $k+1$ forward passes per iteration, whereas MeZO requires 2. Thus, the **sample efficiency** (progress per forward pass) only improves by a factor of $2k/(k+1) \approx 2$ for large $k$, not $k$ or $k/\gamma$.

### Conclusion

The claim that BSZO provides a $k/\gamma$ improvement is not supported by the paper's own derivations. The math in Theorem 4.2 shows that $\gamma$ either slows down convergence (for fixed $\eta$) or has no effect on the rate (for optimal $\eta$). The authors' own text following Corollary 4.3 admits that "$\gamma$ slightly reduces the convergence rate," directly contradicting the $k/\gamma$ claim in the abstract.

### Recommended Resolution

The authors should correct the abstract and contributions to state that the method improves robustness and stability through Bayesian shrinkage, but that the iteration complexity improvement is a factor of $k$, which is partially offset by the increased cost per iteration.
