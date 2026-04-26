# Logic & Reasoning Audit: Harmful Overfitting in Sobolev Spaces (d851088e)

## Phase 1: Definition & Assumption Audit

### 1.1 Key Definitions
- **$\gamma$-ANM Interpolator:** A function $f \in W^{k, p}(\R^d)$ satisfying $f(\vx_i) = y_i$ and $\|f\|_{W^{k, p}} \leq \gamma \|f^*\|_{W^{k, p}}$, where $f^*$ is the minimum-norm interpolator.
- **Harmful Overfitting:** Generalization error $\E[\ell(f(\vx), y)]$ remains bounded below by a constant $C > 0$ as $n \to \infty$.

### 1.2 Assumptions Analysis
- **Assumption 3.3 (Marginal Regularity):** Assumes the data density $p_{\vx}$ is bounded below by $c_{\mc{D}} > 0$ on the entire domain $\overline{\Omega}$. This implies the data has full $d$-dimensional support.
- **Assumption 3.6 (Bayes-optimal Regularity):** Assumes $f_{\bayes} \in W^{k, p}(\R^d)$. This ensures that the ground truth is as smooth as the model's inductive bias.
- **Sobolev Constraint:** $k \in (d/p, 1.5d/p)$. This is a critical technical constraint.

---

## Phase 2: The Three Findings

### Finding 1: The $1.5d/p$ Smoothness Ceiling
The main result (Theorem 3.7) is restricted to $k < 1.5d/p$. My logical audit of the proof reveals that this bound is an artifact of the concentration technique used for the nearest-neighbor radii $\delta_i$.
- In **Lemma 5.4 (Concentration of the sum)**, the proof requires $\beta < d/2$, where $\beta = kp - d$.
- $kp - d < d/2 \implies kp < 1.5d \implies k < 1.5d/p$.
- This requirement ensures that the second moment of the Sobolev norm contribution of individual "bump functions" ($\E[\delta_i^{-2(kp-d)}]$) is finite, allowing the use of McDiarmid's inequality.
- **Impact:** For $d=1, p=2$, the range is $0.5 < k < 0.75$. This means the theorem **does not cover** the standard $k=1$ case in 1D, which was a core result in prior work (e.g., Rakhlin et al., 2019). While the phenomenon likely persists for smoother functions, the current proof fails to reach them.

### Finding 2: Dimensionality and the "Harmful Volume" Gap
The proof relies on the aggregation of generalization error over "harmful neighborhoods" $B(\vx_i, r)$ around noisy points.
- The total harmful volume scales as $n \cdot r^d$, where $r \sim n^{-1/d}$.
- If the data actually lies on an $m$-dimensional manifold ($m < d$), the nearest neighbor distance $\delta$ scales as $n^{-1/m}$.
- The volume of the $d$-dimensional ball $B(\vx_i, \delta_i)$ would then scale as $(n^{-1/m})^d = n^{-d/m}$.
- The total volume would be $n \cdot n^{-d/m} = n^{1 - d/m}$.
- Since $d > m$, this volume **vanishes** as $n \to \infty$.
- **Conclusion:** The claim that harmful overfitting occurs for "fixed-dimension data" (Introduction) is sensitive to the assumption that the data distribution is fully $d$-dimensional. In manifold-learning settings, minimum-norm interpolators might still exhibit benign overfitting despite these results.

### Finding 3: Sharpness of the $\gamma$-ANM Error Bound
The error lower bound $C \gamma^{-pd/(kp - d)}$ is highly sensitive to the smoothness gap $(kp - d)$.
- As $kp \to d$ (the threshold for continuity), the exponent becomes very large, and the error lower bound collapses for $\gamma > 1$.
- This matches the intuition that "wigglier" functions (those barely satisfying the continuity threshold) can fit noise with less global disruption, whereas smoother functions ($k \gg d/p$) force a larger "harmful neighborhood" to maintain the norm constraint.

---

## Phase 3: Hidden-issue Check
- **Definition Drift:** The paper defines $W^{k, p}$ using the standard derivative-based norm (Eq 2), which implies $k \in \mathbb{N}$. However, the range $(d/p, 1.5d/p)$ often contains no integers for small $d, p$ (e.g., $d=1, p=2$). The paper should clarify if it assumes fractional Sobolev spaces ($k \in \R$) or if the theorem is intended to be vacuous in those regimes.
