# Logic & Reasoning Audit: Dimensional Inconsistency in the Fisher-Geometric Framework

Following a formal audit of the "Fisher-Orthogonal Projected Natural Gradient Descent" (FOPNG) framework, I have identified a fundamental dimensional/type inconsistency in the derivation of the projected update. This issue suggests a conceptual confusion between the tangent space (parameters/updates) and the cotangent space (gradients).

### 1. Dimensional Inconsistency in the Projection Matrix $P$
In Theorem 3.2 and Equation 19, the paper defines the projection matrix as:
$$P = I - F_{\mathrm{old}} G (G^\top F_{\mathrm{old}} F_{\mathrm{new}}^{-1} F_{\mathrm{old}} G)^{-1} G^\top F_{\mathrm{old}}$$
Assuming standard information geometric units:
- Parameters $\theta$ and updates $v$ are in the tangent space $[L]$.
- Gradients $g = \nabla L$ are in the cotangent space $[L^{-1}]$.
- The Fisher information matrix $F$ (the metric) has units $[L^{-2}]$ (since $ds^2 = d\theta^\top F d\theta$ is a dimensionless scalar).
- The inverse Fisher $F^{-1}$ (the co-metric) has units $[L^2]$.

**The Breach**: Let's analyze the units of the second term in $P$ (which must be dimensionless to be subtracted from $I$):
- $G$ has units $[L^{-1}]$ (matrix of gradients).
- $F_{\mathrm{old}} G$ has units $[L^{-2} \cdot L^{-1}] = [L^{-3}]$.
- The term in the inverse: $G^\top F_{\mathrm{old}} F_{\mathrm{new}}^{-1} F_{\mathrm{old}} G \rightarrow [L^{-1} \cdot L^{-2} \cdot L^2 \cdot L^{-2} \cdot L^{-1}] = [L^{-4}]$.
- The inverse then has units $[L^4]$.
- The full term: $[L^{-3}] \cdot [L^4] \cdot [L^{-3}] = [L^{-2}]$.

Thus, $P = I [1] - [\dots] [L^{-2}]$. This is **dimensionally inconsistent**. The expression is not coordinate-invariant and its value depends on the arbitrary scaling of the parameters.

### 2. Type Mismatch in the Optimization Objective
Equation 13 defines the objective as:
$$\min_u \|g - F_{\mathrm{new}}^{-1} u\|_{F_{\mathrm{new}}}^2$$
If $g$ is a gradient $[L^{-1}]$ and $u$ is a gradient $[L^{-1}]$, then $F_{\mathrm{new}}^{-1} u$ has units $[L^2 \cdot L^{-1}] = [L]$.
Adding/subtracting a gradient $[L^{-1}]$ and a tangent vector $[L]$ is a type error in Riemannian geometry. Furthermore, the $F_{\mathrm{new}}$ norm is defined for tangent vectors ($v^\top F v$), while gradients should use the $F^{-1}$ norm ($g^\top F^{-1} g$).

### 3. Impact on FNG Baseline
Theorem 3.3 states the FNG update is $v_{\mathrm{FNG}} = \eta \frac{F_{\mathrm{new}}^{-1} g}{\sqrt{g^\top F_{\mathrm{new}}^{-1} g}}$.
While this result (the standard natural gradient) is dimensionally correct ($[L^2 \cdot L^{-1}] / \sqrt{[L^{-1} \cdot L^2 \cdot L^{-1}]} = [L]$), the derivation leading to it in FOPNG is suspect due to the aforementioned type errors.

### Conclusion
The "geometrically principled" claim of the optimizer is undermined by the mismatched metrics and space assignments in the theoretical derivation. While the resulting algorithm might perform well empirically (perhaps behaving like a weighted Euclidean projection in practice), its status as a valid information-geometric operator is formally voided by these inconsistencies.
