# Logic Audit - Physics as the Inductive Bias for Causal Discovery (5987c872)

## 1. Causal Misattribution in the Diffusion-Only Model

The paper models unknown causal interactions strictly through the diffusion term: $d X_t = g dt + \text{diag}(A X_t) d W_t$, where $A$ represents the causal graph.

**Logical Flaw:** In classical mechanics and most dynamical systems, the "causal" influence of state $X_i$ on $X_j$ is mediated through the drift (the forces). For example, in a mass-spring system, the position of one mass affects the acceleration (drift) of the connected mass.
- By assuming the drift $g$ is fully known and placing unknown interactions in $A$, the model assumes that causality **only affects the stochasticity (volatility)** of the system.
- **Audit Finding:** If the true causal mechanism involves the drift (which is the case for almost all physics-based systems), the MLE for $A$ will attempt to explain the "unexplained" drift variance as stochastic volatility. This leads to **spurious edges** in $A$ that don't represent noise-scaling causality but are instead trying to compensate for the misspecified drift model.

## 2. Information Geometry of the Diffusion MLE

The likelihood for the diffusion parameter $A$ depends on the quadratic variation $[X]_t$. 

**Mathematical Concern:** In continuous-time, the quadratic variation is perfectly observable, making $A$ identifiable. However, in discrete-time (Euler-Maruyama), we estimate $A$ from the squared residuals $(X_{t+1} - X_t - g \Delta t)^2$.
- If the drift $g$ is misspecified (e.g., missing a causal term $\Delta g = A_{true} X_t$), the residuals will be $\epsilon \approx (A_{true} X_t) \Delta t + \text{diag}(A_{noise} X_t) \Delta W_t$.
- The squared residuals will contain a term of order $(\Delta t)^2$, while the noise term is order $\Delta t$.
- As $\Delta t \to 0$, the noise term dominates. But for finite $\Delta t$, the missing drift term $(A_{true} X_t)^2 (\Delta t)^2$ will bias the estimate of $A$.
- **Audit Question:** Does Theorem 2 provide a bound on the recovery error that accounts for **drift misspecification**? If not, the guarantee is fragile in any real-world setting where $g$ is not perfectly known.

## 3. The "Pseudo-Equation Trap" and Identification

The paper claims to avoid the "Pseudo-Equation Trap" by using physics as an inductive bias.

**Logical Gap:** If the physics-based drift $g$ is wrong or incomplete, the model is **forced** to put the remaining causal information into the diffusion $A$. This is just a different kind of "pseudo-equation" where we misidentify a deterministic interaction as a stochastic one. 
- **Audit Question:** The paper lacks a "No-Causality-in-Diffusion" test. If a system has complex drift causality but simple additive noise, will the framework correctly return $A=0$, or will it produce a sparse $A$ that "best fits" the drift-induced variance?

## Conclusion

The structural assumption that unknown causality is purely stochastic (diffusion-based) is a severe limitation that likely leads to misidentification in any system where causality is deterministic. I recommend the authors test the framework on systems where the causal signal is moved from the diffusion to the drift to quantify this "leakage" effect.
