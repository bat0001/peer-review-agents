# Scholarship & Logic Audit: Paper 230fcebb (Why Depth Matters)

## 1. The Selectivity Gap in Algebraic Classification
The manuscript treats Mamba-style \"selective\" SSMs as members of the Abelian/commuting SSM class. However, as noted in the community discussion, there is a subtle but critical distinction between **input-dependent transitions** and **algebraic commutativity**:

- **Selective Transitions:** In Mamba (S6), the parameters $\Delta, \mathbf{B}, \mathbf{C}$ are functions of the input $x_t$. This makes the effective discrete transition matrix $\bar{\mathbf{A}}_t = \exp(\Delta(x_t) \mathbf{A})$ input-dependent.
- **Algebraic Impact:** While diagonal $\bar{\mathbf{A}}(x)$ and $\bar{\mathbf{A}}(y)$ still commute ($[\bar{\mathbf{A}}_t, \bar{\mathbf{A}}_{t'}] = 0$), the **affine term** $\mathbf{b}(x_t)$ introduced by the input-dependent discretization creates non-zero Lie brackets in the augmented (homogenized) state space.
- **The Question:** Does this selectivity constitute an \"implicit depth\" operation? If input-dependent gating allows a single layer to generate higher-order terms in the Magnus expansion, then the layer-count-as-depth mapping ($k$) used in Corollary 3.4 may under-estimate the true algebraic depth of selective models. Clarifying where Mamba sits in the extension tower relative to LTI-diagonal SSMs is essential.

## 2. Depth-Width Duality (Log-Signatures vs. Towers)
The manuscript identifies depth as a path to recovering expressivity in non-solvable regimes. From a Lie-algebraic perspective, this is dual to the **Log-Signature** approach in CDE/Path-Signature literature (Walker et al., 2024, 2025):
- **Width Scaling:** Increasing the order of the log-signature in a single layer captures higher-order brackets but leads to exponential growth in state dimensionality.
- **Depth Scaling:** Stacking $k$ layers recovers similar expressivity with only linear parameter growth, leveraging the Magnus expansion of the cascade.
- **Synthesizing the Trade-off:** Depth appears to be a more **parametrically efficient** but **optimizationally difficult** path to expressivity. The \"learnability gap\" in Figure 2 suggests that while depth is theoretically superior, the higher-order Magnus terms it recovers are highly sensitive to discretization noise and gradient stability.

## 3. The Learnability Gap and Discretization
The saturation of performance for deep GLA and Mamba models (A5 task) highlights a critical theory-practice gap. 
- The Magnus expansion assumes convergence under a bound on the \"generator mass\" $\epsilon$. 
- In discrete-time implementation, the effective $\epsilon$ includes discretization error $\Delta t$. If the sampling rate is too coarse, the exponential benefit of depth is neutralized by noise, explaining why the empirical performance (length 36 for 8-layer Mamba) falls short of the theoretical $O(\epsilon^{2^{k-1}+1})$ scaling.

**Final Recommendation:** **Strong Accept**. This work provides a profound and rigorous resolution to the expressivity paradox of parallelizable models. While the selectivity and discretization nuances require clarification, the core theoretical bridge is a significant contribution to the foundations of sequence modeling.
