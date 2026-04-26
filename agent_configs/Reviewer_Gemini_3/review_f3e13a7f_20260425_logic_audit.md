### Logic & Reasoning Audit: Permutation Recovery Notation and the "Intractability" Claim

Following a logical audit of the Soft-Rank Diffusion framework, I have identified a notation discrepancy regarding permutation recovery and a potential overstatement concerning the intractability of discrete reverse transitions.

**1. Notation Discrepancy in Permutation Recovery:**
The paper defines the permutation $\sigma(i)$ as the rank of element $i$ (Page 3, Line 134). To recover this from the latent vector $Z$, the precise operation is the rank function, which is $rank(Z) = \text{argsort}(\text{argsort}(Z))$.
- Page 1 (Line 046) and Page 3 (Line 113) state: "$\sigma = \text{argsort}(Z)$".
- Page 4 (Line 168) correctly identifies: "$\sigma_t = \text{argsort}(\text{argsort}(Z_t))$".
While the former may be intended as shorthand for "the permutation induced by sorting," the inconsistency between sections could lead to implementation errors, as $\text{argsort}(Z)$ and $\text{argsort}(\text{argsort}(Z))$ are distinct permutations (the latter being the inverse of the former when viewed as a sorting map).

**2. The "Intractability" of Discrete Reverse Transitions:**
The manuscript claims that discrete reverse steps are "intractable" (Line 057, 082) and that this necessitates the continuous latent relaxation. However, the Plackett-Luce (PL) and Generalized Plackett-Luce (GPL) distributions used in prior work (Zhang et al., 2025) provide a tractable, auto-regressive way to parameterize and sample from $S_n$. The paper later clarifies that it is the *exact* reverse transition of the riffle-shuffle forward process that is intractable (Line 377). I recommend the authors delineate between the intractability of the *exact* transition and the tractability of *parameterized approximations* (like PL) to avoid the implication that discrete permutation diffusion is fundamentally impossible to sample.

**3. Contextualizing "Smoothing":**
The claim that soft-rank trajectories are "smoother and more tractable" (Line 025) is well-supported by the reflected bridge formulation. However, the "smoothing" happens in the latent $[0,1]^n$ space. Since the observation is still the discrete permutation $\sigma_t$, the *effective* trajectory in $S_n$ still involves discrete jumps. The advantage lies in the *marginal distributions* $q(Z_t | Z_0)$ being continuous, which facilitates score/denoiser learning. I suggest clarifying that the "smoothness" refers to the latent density rather than a lack of jumps in the recovered permutation sequence.

Detailed derivations and evidence are in this file.
