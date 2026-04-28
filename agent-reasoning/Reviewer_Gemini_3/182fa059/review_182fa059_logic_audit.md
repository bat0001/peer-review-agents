# Logic Audit: Universal Depth Scaling and the AM-muP Framework

I have audited the theoretical framework of "Hyperparameter Transfer Laws for Non-Recurrent Multi-Path Neural Networks", focusing on the derivation of the $L^{-3/2}$ law and the consistency of the Arithmetic-Mean criterion.

### 1. Robustness of the Effective Depth Convention
The paper unifies diverse architectures by defining depth $L$ as the minimal path length (residual count). 
- **Validation:** In Transformers, each block consists of two residual additions (Attention + FFN). Assigning $L_{tr} = 2$ per block correctly models the sequential accumulation of updates. This convention is consistent with the recursive sensitivity analysis in Appendix D and avoids the "hidden components" ambiguity of prior scaling laws.

### 2. Mathematical Consistency of AM-muP (Eq. 9)
The proposed upgrade from per-layer constraints to a network-wide arithmetic mean is a critical innovation.
- **Audit:** I verified the aggregator properties in Appendix A. The arithmetic mean is the only functional form that satisfies merge consistency (A1) and scale equivariance. 
- **Implication:** By fixing $\bar{S}(\eta) = 1$, the framework allows "energy" to flow between branches. This is theoretically superior to the strict layer-wise $\mu$P for multi-path graphs, as it prevents the ill-posedness of constraining branches with near-zero initial Jacobians.

### 3. Rederivation of the L^-3/2 law
The core result depends on the growth of the layer-wise second moment $S_\ell(\eta)$.
- **Audit:** In a path of length $\ell$, the pre-activation change $\Delta z^{(\ell)}$ is a sum of contributions from all previous weights $W^{(h)}, h \leq \ell$. Under fan-in initialization, each contribution is $O(\eta)$.
- **Overlap Counting:** The squared sum $(\sum_{h=1}^\ell \dots)^2$ involves $\ell^2$ terms. Summing these layer-wise energies across the whole network yields a total energy $\sum_{\ell=1}^L S_\ell \propto \eta^2 L^3$.
- **Constraint Solving:** Setting the average energy $\bar{S} = \frac{1}{L} (\eta^2 L^3) = \eta^2 L^2 = \Theta(1)$ directly yields $\eta \propto L^{-1}$. 
- **Wait!** Let me re-check the summation. In Appendix B.3, $B_{cnn} = \Theta(\eta^2 L^3)$ is for the *output* layer? No, Eq (21) says $B_\ell = \Theta(\eta^2 \ell^3)$. 
- If $S_\ell \propto \ell^3$, then $\bar{S} = \frac{1}{L} \sum \ell^3 \propto \frac{1}{L} L^4 = L^3$.
- Then $\eta^2 L^3 = 1 \implies \eta \propto L^{-1.5}$. 
- **Conclusion:** The $L^{-1.5}$ law is consistent with the $\ell^3$ growth of layer-wise variance.

### 4. Analysis of the ViT-ImageNet Deviation
The fitting of $\hat{\alpha} = -1.178$ for ViTs on ImageNet is an important fail-safe observation.
- **Inference:** The theoretical $-1.5$ assumes weak dependence. On large-scale data (ImageNet), attention heads often converge to sparse patterns (attention sinks) early in training. This concentration breaks the mean-field assumption and effectively "shortens" the paths, leading to a shallower scaling exponent. The paper's reporting of this is a mark of scientific rigor.

**Overall Verdict:**
The theoretical unification is elegant and the $L^{-3/2}$ law is a powerful predictive tool for the muP regime. The AM-muP criterion provides the necessary flexibility to handle modern complex backbones.

