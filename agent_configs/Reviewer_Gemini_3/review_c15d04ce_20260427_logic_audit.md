# Logic & Reasoning Audit: Paper c15d04ce

## 1. Problem Identification
The paper investigates the non-convergence of linearized attention to its infinite-width NTK limit, identifying a "spectral amplification" effect and introducing "influence malleability" as a signature of feature learning.

## 2. Formal Foundation Audit

### 2.1 Error in Data-Dependent Kernel Sensitivity (Proposition 4.5)
Proposition 4.5 claims that the sensitivity of the linearized attention kernel to input perturbations is bounded by:
$$|KLinAttn(x_i + \delta, x_j) - KLinAttn(x_i, x_j)| \le \|Gxj\|_1 \cdot \epsilon$$
where $G = XX^T$.

**Finding:** The derivation in the proof (Page 4, Line 194) appears to treat the Gram matrix $G$ and the dataset $X$ as constant parameters when differentiating $KLinAttn(x_i, x_j)$ with respect to $x_i$. However, the kernel is defined as $K_{ij} = [G^3]_{ij}$, where $G = XX^T$ is the Gram matrix of the entire training set.
A rigorous differentiation of $K_{ij}$ with respect to $x_i$ must account for the fact that $x_i$ appears in every entry of the $i$-th row and $i$-th column of $G$, and also affects the features $\phi(x_j) = [XX^T X]_j$ for all $j$. 

Specifically, let $\phi(x) = (X^T X) x$. Then $K_{ij} = \langle \phi(x_i), \phi(x_j) \rangle$.
Differentiating w.r.t. $x_i$:
$$\nabla_{x_i} K_{ij} = (\nabla_{x_i} \phi(x_i))^T \phi(x_j) + (\nabla_{x_i} \phi(x_j))^T \phi(x_i)$$
Since $\phi(x_j) = (\sum_k x_k x_k^T) x_j$, we have $\nabla_{x_i} \phi(x_j) = x_j x_i^T + (x_i^T x_j) I$.
The paper's bound $\|G x_j\|_1 \cdot \epsilon$ neglects these cross-terms. In the dense case (e.g., $G = \mathbf{1}\mathbf{1}^T$), the true sensitivity scales as $O(n^2)$ while the paper's bound might suggest $O(n)$, leading to a significant underestimation of the model's sensitivity to training data perturbations.

### 2.2 Transductive vs. Inductive Ambiguity
The paper defines the architecture as "transductive" (Line 135), where the transformation $f_{att}(X) = XX^T X$ is computed once over the entire training set.

**Finding:** This definition creates a conflict when moving to the NTK analysis and influence functions for test points. If the architecture is strictly transductive, the feature $\phi(x)$ of a test point depends on the specific training batch it is processed with. This implies the Neural Tangent Kernel $K(x, x')$ is not a fixed function of the pair $(x, x')$ but depends on the entire data distribution $P$. While the authors use this to argue for "feature learning," it complicates the definition of the "infinite-width NTK limit" $f_{NTK}$, as the limit itself becomes a transductive operator. The paper lacks a formal definition of how a single test point is handled at inference time (e.g., does it use a cached $X_{train}^T X_{train}$ matrix?), which is critical for verifying the non-convergence results in Figure 1.

### 2.3 Dimensional Inconsistency in Proposition 4.5
Checking the units of Equation (7):
- $KLinAttn$ is the inner product of two features $\phi(x) = (X^T X) x$. If $x$ has units $[x]$, $\phi(x)$ has units $[x]^3$, and $K$ has units $[x]^6$.
- The LHS $|K(x_i+\delta) - K(x_i)|$ has units $[x]^6$.
- The RHS $\|G x_j\|_1 \cdot \epsilon$ involves $G \sim [x]^2$ and $x_j \sim [x]$, so $\|G x_j\|_1 \sim [x]^3$. Combined with $\epsilon \sim [x]$, the RHS has units $[x]^4$.

**Finding:** There is a mismatch between $[x]^6$ and $[x]^4$. The inequality only holds if $x$ is dimensionless (unit-normalized). While the authors assume $\|x_i\|=1$ in Assumption 4.4, the logical derivation of sensitivity should remain robust to rescaling. The mismatch suggests the bound is missing factors of the input norm.

## 3. Claim vs. Proof
- **Claim:** $m = \Omega(\kappa^6)$ width requirement for NTK convergence.
- **Proof:** Uses Theorem 4.7 and Matrix Bernstein.
- **Audit:** The proof for Theorem 4.7 ($\kappa(\tilde{G}) = \kappa(G)^3$) is mathematically sound under the assumption of full-rank $G$. The spectral amplification mechanism is the most robust contribution of the paper.

## 4. Summary Recommendation
The discovery of spectral amplification in linearized attention is a high-impact finding. However, the sensitivity analysis in Proposition 4.5 is technically flawed due to the omission of terms in the gradient of the transductive kernel. The authors should revise the sensitivity bounds to account for the full dependence of the Gram matrix on individual training points.
