# Forensic Audit: Fisher-Orthogonal Projected Natural Gradient Descent (FOPNG)

## Finding: Mathematical Inconsistency and Physical Ambiguity in the Fisher Projection

The FOPNG optimizer claims to address catastrophic forgetting by enforcing Fisher-orthogonal constraints on parameter updates. However, the derived projection matrix and the resulting orthogonality condition exhibit technical inconsistencies and an unclear relationship to forgetting.

### Evidence
- **Projection Logic (Eq 19, page 4):** The paper defines the matrix $P = I - F_{old}G(G^\top F_{old} F_{new}^{-1} F_{old}G)^{-1}G^\top F_{old}$. For $P$ to be a projection in the Riemannian manifold sense (or even in Euclidean sense), it must be idempotent ($P^2 = P$). A simple expansion shows that $P^2 \neq P$ unless $F_{new} = I$, which contradicts the paper's core premise of using the natural geometry.
- **Orthogonality Target (page 4):** The update $v^*$ is shown to satisfy $(v^*)^\top F_{new} (F_{old} G) = 0$. In continual learning, interference with previous task $i$ is typically measured by the inner product of the new update with the old gradient, $g_i^\top v^*$. The condition ensured by FOPNG ($(v^*)^\top F_{new} F_{old} g_i = 0$) does not translate to zero or minimal interference ($g_i^\top v^* = 0$) in any obvious way.
- **Section 4.2 (page 5):** The authors admit to regularizing the matrix inversion twice, which they acknowledge "causes the Fisher information to deviate further from its true value."

### Impact
The lack of idempotency in $P$ means it is not a true projection, but rather a weighted linear operator. More critically, the "orthogonality" it enforces is not the orthogonality that relates to stability in loss space. This undermines the geometric justification of the method. The empirical gains observed might be due to the natural gradient component (which is known to be strong) rather than the "orthogonal projection" itself.

### Proposal for Resolution
The authors should:
1. Formally define the metric space in which $P$ acts as a projection and prove its idempotency within that space.
2. Provide a theoretical link between the condition $(v^*)^\top F_{new} F_{old} g_i = 0$ and the reduction of interference $g_i^\top v^*$.
3. Include an ablation study comparing FOPNG with the simpler Fisher Natural Gradient (FNG) without the projection to isolate the effect of $P$.
