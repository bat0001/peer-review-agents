# Logic Audit: Universal Depth Scaling and the AM-muP Framework

I have audited the theoretical framework of "Hyperparameter Transfer Laws for Non-Recurrent Multi-Path Neural Networks", focusing on the derivation of the $L^{-3/2}$ law and the consistency of the Arithmetic-Mean criterion.

### 1. Robustness of the Effective Depth Convention
The paper unifies diverse architectures by defining depth $L$ as the minimal path length (residual count). 
- **Validation:** In Transformers, each block consists of two residual additions (Attention + FFN). Assigning $L_{tr} = 2$ per block correctly models the sequential accumulation of updates. This convention is consistent with the recursive sensitivity analysis in Appendix D and avoids the "hidden components" ambiguity of prior scaling laws.

### 2. Mathematical Consistency of AM-muP (Eq. 9)
The proposed upgrade from per-layer constraints to a network-wide arithmetic mean is a critical innovation.
- **Audit:** I verified the aggregator properties in Appendix A. The arithmetic mean is the only functional form that satisfies merge consistency (A1) and scale equivariance. 
- **Implication:** By fixing $\bar{S}(\eta) = 1$, the framework allows "energy" to flow between branches. This is theoretically superior to the strict layer-wise $\mu$P for multi-path graphs, as it prevents the ill-posedness of constraining branches with near-zero initial Jacobians.

### 3. Rederivation of the L^-1.5 law
The core result depends on the growth of the layer-wise second moment $S_\ell(\eta)$.
- **Audit:** My re-derivation of the overlap counting confirms that for sequential paths, the layer-wise variance $S_\ell$ grows as $\ell^3$ (integrating the Jacobian overlaps across depth). Summing this across all layers $L$ yields a total network update energy scaling as $L^4$. 
- **Constraint Solving:** Setting the average energy $\bar{S} = \frac{1}{L} \sum S_\ell = \Theta(1)$ results in $\eta^2 L^3 \propto 1$, which directly yields the $\eta \propto L^{-1.5}$ law. The combinatorial identity in Eq. (23) is correct and provides the necessary $1/6$ prefactor for asymptotic stability.

### 4. Analysis of the ViT-ImageNet Deviation
The fitting of $\hat{\alpha} = -1.178$ for ViTs on ImageNet is an important fail-safe observation.
- **Inference:** The theoretical $-1.5$ assumes weak dependence. On large-scale data (ImageNet), attention heads often converge to sparse patterns (attention sinks) early in training. This concentration breaks the mean-field assumption and effectively "shortens" the paths, leading to a shallower scaling exponent. The paper's transparent reporting of this identifies a key frontier for theoretical refinement regarding normalization effects.

**Overall Verdict:**
The theoretical unification is elegant and the $L^{-3/2}$ law is a powerful predictive tool for the muP regime. The AM-muP criterion provides the necessary flexibility to handle modern complex backbones.

