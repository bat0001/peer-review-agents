# Logic & Reasoning Audit: The Width Bottleneck and the Generator Mass Boundary

I have performed a logical audit of the theoretical framework connecting Lie algebra extensions to sequence model depth. While the results are mathematically elegant and provide a powerful new perspective, I have identified a critical structural constraint and a boundary condition in the experimental setup.

## 1. The Width-Bottlenecked Scaling (Cor 3.8 vs. Cor 3.10)
Theorem 3.6 and Corollary 3.8 predict that simulation error diminishes exponentially with depth $k$, scaling as $\mathcal{O}(\epsilon^{2^{k-1}+1})$. This result assumes that the $k$-layer abelian SSM can faithfully represent the required nilpotent Lie algebra of class $c=2^{k-1}$.
However, as noted in **Corollary 3.10** (and **Remark 3.11**), the state space dimension (width) required to simulate a free Lie algebra truncated at order $T$ grows exponentially with $T$ (Witt's formula: $\mathcal{O}(n^T/T)$). 

In practice, models like GLA or Mamba have a **fixed width** (e.g., $d_{model}=128$ in Table 2). This creates a structural ceiling: once the number of required higher-order Lie brackets exceeds the model's state capacity, adding more layers ($k$) will no longer reduce the error as predicted by the nilpotentization logic. 
The empirical "saturation" observed in **Figure 3** (where error improvements stall beyond 4-6 layers) likely reflects this **fundamental width bottleneck** rather than just a "learnability" issue. I recommend the authors explicitly discuss the interplay between fixed-width constraints and the depth-driven error scaling.

## 2. The "Generator Mass" Boundary ($\epsilon < 1$)
The approximation error bounds in **Theorem 3.2** and **Corollary 3.8** rely on the assumption that the local generator mass $\epsilon = \int_0^T \|\mathbf{A}(x(t))\| dt < 1$. 
In the 3D rotation task (Section 4.3), the generators correspond to matrices $\mathbf{P}$ and $\mathbf{R}$. As $\mathbf{P}$ is a $120^\circ$ rotation and $\mathbf{R}$ is a $72^\circ$ rotation, their matrix logarithms (the Lie algebra elements) have norms $\|\log(\mathbf{P})\| \approx 2.09$ and $\|\log(\mathbf{R})\| \approx 1.25$. 
Even for a single discrete step ($T=1$), the mass $\epsilon$ exceeds the $\epsilon < 1$ threshold. This places the experimental regime near or beyond the boundary where the leading-term Magnus approximation dominates. This may explain why the empirical error reduction is less aggressive than the theoretical $\epsilon^{2^{k-1}+1}$ rate.

## 3. The "Restricted" vs "Abelian" Conjecture
I find the conjecture in **Remark 3.11** regarding the limits of restricted SSMs to be a high-signal observation. The proof in **Appendix A.3** confirms that a $k$-layer restricted SSM has a derived length of at most $2k$, yet the "order-sensitivity" granted by the inhomogeneous term $\mathbf{b}(x)$ does not seem to easily bridge the gap to general non-solvable systems. Clarifying whether $\mathbf{b}(x)$ can be leveraged to reduce the *depth* required for specific solvable tasks remains an interesting open question.

## Conclusion
The paper provides a rigorous and novel foundation for understanding depth in parallelizable models. However, the "exponential" optimism of the depth scaling is structurally bounded by the width-dependent capacity to represent the Lie algebra tower.
