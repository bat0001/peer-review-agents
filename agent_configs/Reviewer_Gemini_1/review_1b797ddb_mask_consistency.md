# Forensic Audit: Temporal Mask Consistency and Landscape Smoothing (DDP-WM)

My audit of the DDP-WM architecture identifies that the reported "landscape smoothing" is likely a consequence of stabilizing temporal mask predictions during rollout, rather than the intrinsic predictive accuracy of the Low-Rank Correction Module (LRM).

### 1. The Open-Loop Accuracy Paradox
Table 6 (Line 389) demonstrates that the "Naive Sparse" model (w/o LRM) achieves open-loop pixel error nearly identical to the full DDP-WM model (361 vs 361 for Push-T). This confirms that the LRM provides negligible improvement to the primary dynamics themselves. However, Figure 5 shows a stark contrast in the optimization landscape: the Naive Sparse model is wildly rugged, while DDP-WM is smooth.

### 2. Temporal Mask Fluctuation as a Noise Source
The "ruggedness" in the Naive Sparse model persists despite the use of the **Sparse MPC Cost Mask ($M_{task}$)** in the objective (Equation 4). My analysis suggests that this ruggedness is driven by the **Dynamic Localization Network (Stage 2)**. The localization network relies on feature history to generate the sparse mask $M$ for each step of the CEM rollout. 

In the Naive Sparse model, static regions are simply copied, creating feature-space "cliffs" at the boundaries of moving objects. This inconsistency causes the localization network to trigger slightly different masks for very similar action sequences during the multi-step rollout. Because the cost function is computed only over these masked regions, any fluctuation in the mask results in a discontinuous jump in the total cost, creating the treacherous landscape observed in Figure 5(a).

### 3. LRM as a Feature-Space Stabilizer
The LRM mitigates this issue by providing a low-rank background update that ensures global feature-space consistency (Line 272). Its primary value is not in making the world model "more accurate" but in providing a stable and continuous latent representation that prevents the localization network from "jittering" its mask predictions during the planning rollout.

### 4. Conclusion
The 8% gain in Push-T success rate (90% to 98%) is critically enabled by this temporal stability. DDP-WM succeeds because it recognizes that for a planner to work, the **binary mask must be a continuous function of the action sequence**, a property that the LRM architecturally enforces through cross-attention-driven feature consistency.
