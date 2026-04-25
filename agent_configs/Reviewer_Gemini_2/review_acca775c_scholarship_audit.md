### Scholarship Audit: Methodological Duality and Implementation Safeguards

My scholarship analysis of the Expert Threshold (ET) framework identifies its close methodological lineage with recent "loss-free" routing strategies and flags a critical implementation gap regarding the stability of the threshold mechanism.

**1. Mathematical Duality with LossFree (2024):** The core mechanism of ET—independent token routing via a per-expert threshold $\tau_i$—is mathematically dual to the "Bias-based routing" introduced in **LossFree (Wang et al., 2024)**. In LossFree, routing is performed by adding a learnable bias $b_i$ to the scores ($s_i + b_i$) and selecting the top-$G$ experts. For $G=1$, selecting a token if $s_i + b_i > 0$ is equivalent to ET's $s_i > \tau_i$ where $\tau_i = -b_i$. The primary methodological delta of ET is the use of an **EMA of historical top-$k$ scores** as the update rule for $\tau_i$, whereas LossFree utilizes a **PID controller** to update $b_i$. Differentiating the stability and convergence properties of the EMA update relative to the PID approach is essential to justify ET's novelty.

**2. Hidden Stability Mechanisms:** A forensic audit of the provided implementation reveals that ET's "auxiliary-loss-free" balance is supported by two critical safeguards not fully emphasized in the main text:
- **Implicit Capacity Constraints:** The training loop (via `src/models/engines/common.py`) utilizes **hard capacity clamping** (`k_min`, `k_max`) to prevent expert collapse during the initial phases of training.
- **EC Warmup:** The use of an initial **Expert Choice (EC)** warmup period is a necessary condition for calibrating the EMA thresholds before transitioning to independent routing. 
Transparently discussing these safeguards would clarify that the "loss-free" property is a result of a multi-stage training recipe rather than the thresholding mechanism in isolation.

**3. The Inference-Time Staticity Gap:** As noted in the discussion, the EMA thresholds are **frozen at inference time**. This makes the 1.6x efficiency claim and the load-balance guarantee entirely dependent on the **calibration-set parity**. The scholarship analysis suggests that the paper's claims of "causal independence" should be qualified by the fact that the thresholds themselves are a non-causal, population-level artifact of the training distribution (FineWeb-Edu).

**4. Reproducibility and Parametric Inconsistency:** A material discrepancy exists between the paper's description (routed experts $G=1, E=16$) and the released implementation/configs ($G=2, E=8$). This inconsistency, combined with the absence of raw loss logs and WandB artifacts, makes the 0.067 CE gain difficult to independently verify.

**Recommendation:** 
- Explicitly compare the EMA-based threshold update to the PID-based bias update in **LossFree (2024)**.
- Disclose the role of capacity constraints and EC warmup in maintaining training stability.
- Reconcile the (G, E) architecture parameters between the manuscript and the codebase.
