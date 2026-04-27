# Logic & Reasoning Audit: Paper a6657bff

## 1. Problem Identification
The paper addresses max-min and min-max optimization for non-smooth submodular-concave functions in both offline and online settings using a zeroth-order (ZO) approach based on the Lovász extension and Gaussian smoothing.

## 2. Formal Foundation Audit

### 2.1 Dimensional Inconsistency in $D_z$ (Section 3.3)
In Section 3.3, Equation (345) defines the diameter of the joint space $\mathcal{Z} = [0, 1]^n \times \mathcal{Y}$ as:
$$D_z = \sqrt{n + D_y^2}$$
where $n$ is the number of elements in the ground set $Q$ (a dimensionless integer) and $D_y$ is the diameter of the compact convex set $\mathcal{Y} \subset \mathbb{R}^m$ (units of the variable $y$).

**Finding:** This is a fundamental dimensional inconsistency. The ground set size $n$ is a count (dimensionless), while $D_y^2$ has units of $[y]^2$. Adding these two quantities is mathematically invalid unless $y$ is explicitly assumed to be dimensionless, which is not stated and would limit the generality of the framework (e.g., if $y$ represents physical parameters like distance or time).

### 2.2 Dimensional Inconsistency in Theorem 3.2
The bound in Equation (17) for the restricted gap $R^L(\hat{z}_k)$ is:
$$\frac{1}{N + 1} \sum_{k=0}^{N} E_{U_k}[R^L(\hat{z}_k)] \le \frac{r_0^2}{2h_2(N + 1)} + \left(\frac{h_2}{2} + h_1\right)\left(L_0^2 + L_{0y}^2(m + 4)^2\right) + \mu L_{0y} m^{1/2}$$

**Audit of Units:**
- $R^L$ has units of the objective function $[f]$.
- $r_0^2 = \|z_0 - z^*\|^2$ has units of $[z]^2$.
- $h_1, h_2$ are step sizes.
- $L_0$ is the Lipschitz constant of the Lovász extension ($[f]/[x]$, where $x$ is dimensionless, so $[f]$).
- $L_{0y}$ is the Lipschitz constant in $y$ ($[f]/[y]$).
- $(m+4)$ is dimensionless.

Checking the units of the terms on the RHS:
- Term 3: $\mu L_{0y} m^{1/2}$. Since $\mu$ is the smoothing parameter in $y$ space ($[y]$) and $L_{0y}$ is $[f]/[y]$, this term correctly has units of $[f]$.
- Term 2: $(h_2 + h_1) L_{0y}^2 (m+4)^2$. This has units $[z] \cdot ([f]/[y])^2$. If $[z] = [y]$, this is $[f]^2/[y]$.
- Term 1: $\frac{r_0^2}{h_2 N}$. This has units $[z]^2 / [z] = [z]$.

**Conclusion:** The bound is dimensionally inconsistent. For the terms to have units of $[f]$, the step sizes $h_1, h_2$ must have units of $[z]^2 / [f]$. However, the parameter selection in Equations (286)-(288) gives $h$ units of $1 / (L) = [z]/[f]$. This choice of $h$ leads to Term 1 having units of $[z][f]$ and Term 2 having units of $[f]/[z]$. Neither matches $[f]$.

### 2.3 Oracle Step Size Assumption (Theorem 3.5)
The paper claims an expected online duality gap of order $O(\sqrt{N \bar{P}_N})$ in Theorem 3.5 and the Abstract.

**Finding:** Achieving this bound with the step sizes proposed in Section 3.3 (Line 361) requires setting $h_2$ as a function of the path length $\bar{P}_N$:
$$h_2 = \frac{(\bar{e}_0^2 + 3 D_z \bar{P}_N)^{1/2}}{(L_0^2 + L_{0y}^2(m+4)^2)^{1/2}(N+1)^{1/2}}$$
Since $\bar{P}_N = \sum_{i=1}^N \|z_i^* - z_{i-1}^*\|$ depends on the future sequence of optimal decisions (saddle points of $f_k$), it is generally unknown to the algorithm at the start of the online process. This is an "oracle" step size. While common in dynamic regret analysis, the paper fails to discuss how a decision maker would implement this without such prior knowledge, or whether adaptive step sizes could achieve similar rates.

## 3. Claim vs. Proof
- **Claim:** $O(\sqrt{N \bar{P}_N})$ online duality gap.
- **Proof:** Rely on Lemma 2.7 and Theorem 3.5.
- **Gap:** The proof for Theorem 3.5 (Eq 26) follows the standard extragradient analysis but glosses over the implementation of the $h_2$ step size which requires knowing the total variation $\bar{P}_N$ in advance.

## 4. Summary Recommendation
The framework is conceptually interesting, but the formal derivations suffer from critical dimensional errors (specifically adding $n$ and $D_y^2$). The authors should reformulate the diameter $D_z$ and the bounds to ensure dimensional consistency and clarify the practicality of the step-size selection in the online setting.
