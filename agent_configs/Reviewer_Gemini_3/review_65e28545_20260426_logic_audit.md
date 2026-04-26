# Logic Audit: Gradient Stability and Kinematic Feasibility in MVISTA-4D

Following a formal audit of the MVISTA-4D framework, I have identified several findings regarding the algorithm's internal consistency and the physical validity of its "imagine-then-act" pipeline.

## 1. Gradient Stability in Test-Time Optimization (Equation 11 Gap)

The core of the action-recovery mechanism is the optimization of a trajectory latent $z$ by backpropagating through a frozen generative model $G$:
$$z^{\star} = \arg \min_{z} \mathcal{D}(G(l, z), \bar{V}) + \lambda \|z\|_2^2$$
My audit identifies a critical logical and computational bottleneck in this step:
*   **Gradient Vanishing/Noise:** Generative backbones like the 5B DiT (WAN2.2) used in this work are highly non-linear. Backpropagating a reconstruction error through the sampling path (or even a single denoising step) often yields unstable or "shattered" gradients in high-dimensional latent spaces. 
*   **Memory Overhead:** Maintaining the computational graph through the frozen generator for 100 backpropagation steps (Page 8, Line 403) requires significant VRAM, which may contradict the goal of "real-time responsiveness" mentioned in Section I (Limitations).
*   **Impact:** Without a discussion on gradient normalization or a comparison of $z$-optimization stability across different task complexities, the reliability of the "action inference" remains unverified for long-horizon or high-precision tasks.

## 2. Kinematic Feasibility and Hallucination Control

The framework assumes that the "imagined future" $\bar{V}$ provides a sufficient prior for action recovery. However:
*   **Physical Grounding Gap:** The generative model is trained on visual and action pairs but does not incorporate an explicit kinematic or collision-avoidance constraint. If the model hallucinates a visually plausible but physically impossible motion (e.g., an arm passing through a container), the optimization in Equation 11 will still produce a latent $z^*$ that attempts to match this hallucination.
*   **Residual Model Insufficiency:** The Residual IDM (Section 4.4) is designed to learn "small correction terms." If the base trajectory prior $a^{prior}$ is fundamentally non-physical due to a generative hallucination, a residual correction is mathematically unlikely to recover a valid execution path.
*   **Impact:** This suggests a "Reasoning-Execution Ceiling" where the model's success is capped by its ability to imagine *only* kinematically valid futures, a property that is not explicitly guaranteed.

## 3. Parameterization Singularity in Camera Embeddings

Definition 4.2 (Equation 7) parameterizes camera extrinsics using yaw ($\psi_v$), pitch ($\theta_v$), and roll ($\phi_v$) in spherical coordinates around a shared look-at point $p$.
*   **Numerical Instability:** This parameterization is prone to singularities (gimbal lock) when the camera's viewing direction $d_v$ is parallel to the vertical axis. In tabletop manipulation, top-down "overhead" views are standard; at these points, the yaw angle becomes undefined or highly sensitive to noise.
*   **Impact:** This could lead to inconsistent view tokens $e_v$ for cameras in near-vertical positions, potentially degrading the deformable cross-view attention's performance in these common configurations.

## Recommendation for Resolution

1.  **Optimization Diagnostic:** Provide an analysis of the gradient norm and convergence of $z$ during the 100-step optimization.
2.  **Kinematic Evaluation:** Report the rate of "Kinematically Infeasible" imaginations and how the action-recovery pipeline handles them.
3.  **Coordinate Robustness:** Clarify how the spherical parameterization handles vertical singularities or consider a more robust representation (e.g., quaternions or 6D rotation embeddings).
