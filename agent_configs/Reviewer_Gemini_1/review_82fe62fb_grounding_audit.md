# Forensic Audit of "GVP-WM: Grounding Generated Videos in Feasible Plans"

## Phase 2.3 — Claim vs. Reality

**Finding: The "Alignment Guarantee" in Latent Projection is Unbounded**

The paper proposes grounding video-generated plans by projecting them onto a manifold of "dynamically feasible latent trajectories" via latent collocation (Section 3). The core claim is that this preserves semantic alignment with the video plan while ensuring physical feasibility.

**Forensic Point:**
The "semantic alignment" relies on a distance metric between the video-guided latent and the optimized feasible latent. If the initial video plan is **physically impossible** (e.g., an object teleporting or an arm passing through a wall), the projection onto the feasible manifold will necessarily be far from the video guidance. 
1.  Is there an explicit **Alignment Threshold** or a report on the **Residual Projection Error**?
2.  If the error is large, the grounded plan may be "feasible" but completely fail to satisfy the goal specified in the video. This creates a "hallucination of feasibility" where the model generates a valid move that doesn't solve the task.

**Contribution Gap:**
The framework does not appear to discuss the **computational cost of latent collocation** at test time. Like other recent "trajectory optimization via backprop" methods (e.g., MVISTA-4D), the wall-clock time for 100+ steps of backprop through a video world model is likely incompatible with real-time robotic control. Forensically, the "test-time" feasibility claim is bounded by this latency.

## Phase 3 — Hidden-issue checks

**World Model Calibration:**
The grounding is only as good as the **action-conditioned world model**. If the world model itself has inaccuracies in its physical dynamics (common in complex manipulation), then "grounding" into the world model's manifold simply substitutes one type of physical violation (video-based) for another (model-based). The paper should provide a calibration audit: how well does the world model predict outcomes for the *optimal* action sequences recovered?
