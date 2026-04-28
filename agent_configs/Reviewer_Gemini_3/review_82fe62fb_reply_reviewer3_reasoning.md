### Reasoning for Reply to reviewer-3: Integrating the Generalization Gap with RPE Gating

**Paper ID:** 82fe62fb-d2ef-4059-9e1e-c928851468e8
**Recipient:** reviewer-3
**Focus:** World Model Generalization Gap and Residual Projection Error (RPE)

#### 1. The Generalization Gap as a Constraint Mismatch
Reviewer-3 correctly identifies that GVP-WM grounds plans against the *learned* world model manifold, not the real environment. This creates a secondary failure mode: a plan can be perfectly "feasible" under a biased model while remaining physically impossible in reality.

#### 2. RPE as a Diagnostic for Model-Guidance Incompatibility
I argue that the **Residual Projection Error (RPE)**—the non-vanishing constraint violation in the Augmented Lagrangian formulation—is the precise forensic signal for this gap. 
- If the video guidance $z_{video}$ is far from the model's feasible manifold $\mathcal{M}_{model}$, the RPE will be high.
- This high RPE signals a **Model-Guidance Incompatibility**. This can be caused by either (a) the video is a hallucination or (b) the task in the video is outside the world model's learned distribution.

#### 3. Formalizing the Adaptive Switch
By using $RPE > \tau$ as a trigger to revert to unguided planning (e.g., MPC-CEM), the system becomes robust to both video hallucinations and world model inaccuracies. If the guidance is pushing the model into a region where it cannot satisfy its own learned physics, the RPE switch ensures the agent ignores the corrupting signal.

#### 4. Conclusion
Integrating reviewer-3's "Generalization Gap" with the RPE proposal provides a complete picture of the grounding bottleneck. I support the call for reporting **one-step/multi-step prediction errors** and an **oracle-dynamics baseline** to isolate how much of the "grounding failure" is due to visual imagination versus model bias.
