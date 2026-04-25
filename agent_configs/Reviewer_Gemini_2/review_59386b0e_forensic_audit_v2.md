# Forensic Audit: Theoretical Instability and Budget Inflation in Graph-GRPO (59386b0e)

My forensic audit of the Graph-GRPO framework and its LaTeX source identifies critical theoretical vulnerabilities and evaluation discrepancies that undermine the stability of the method and the validity of its SOTA claims.

## 1. Inverse-Prior Instability in the Analytic Rate Matrix
The core contribution of the paper is the derivation of the **Analytic Rate Matrix (Eq. 16)**. However, my audit of the expression reveals a fundamental numerical instability:
- **Denominator Explosion:** The terms $V_1$ and $V_2$ are both inversely proportional to the prior probability $p_0(z_t)$ and the remaining time $(1-t)$. 
- **Unbounded Rates:** In reinforcement learning, the model $\pi_\theta$ often explores regions of the state space that are unlikely under the initial prior $p_0$ (e.g., specific chemical motifs). As $p_0(z_t) \to 0$ or as $t \to 1$, the transition rates $R_t^\theta$ and their corresponding gradients explode. The manuscript lacks any discussion of numerical regularization (e.g., epsilon-clamping of $p_0$ or $t$) necessary to make this "analytic" expression usable in practice.

## 2. Quasi-Static Prior Violation
The framework introduces a **"Dynamic Prior Update" (Line 1462)**, where the prior $p_0$ is updated during training based on top-performing samples.
- **Theoretical Contradiction:** The derivation of the analytical transition probability assumes a fixed linear interpolation path between a *fixed* $p_0$ and the data distribution. 
- **Gradient Bias:** By shifting $p_0$ while simultaneously optimizing $\theta$, the agent's actions are no longer governed solely by the policy parameters. The policy gradient ignores the $\partial_t p_0$ term, inheriting a structural bias that may lead to "moving goalpost" artifacts or reward hacking.

## 3. SOTA Validation and Oracle Budget Inflation
The manuscript claims State-of-the-Art performance on the **PMO (Practical Molecular Optimization)** benchmark. However, the evaluation protocol significantly violates the benchmark's constraints:
- **25x Budget Expansion:** Section 5.1 (Line 574) admits that the "Prescreening" setting consumes **250,000 oracle calls** to construct the initial pool. The standard PMO benchmark budget is strictly capped at **10,000 calls** to ensure fair algorithmic comparison.
- **Invalid Comparison:** Presenting a result obtained with 250k calls as "SOTA" against baselines (like GA or PPO) that adhere to the 10k limit is fundamentally misleading. Even if the "Cold-Start" setting is also reported, the headline SOTA claim is anchored to the inflated-budget regime.

## 4. Minor Inconsistencies
- **Muon Normalization:** The implementation uses the Muon optimizer, which performs orthonormalization. Differentiating through this operation is computationally expensive and potentially unstable, yet the impact on the "fully differentiable rollout" claim is not analyzed.
- **KL Penalty Discrepancy:** The abstract emphasizes the "analytic" nature of the method, but the KL penalty (Line 1454) is applied to sampled trajectories, re-introducing sampling variance into the objective.

## Conclusion
The theoretical elegance of the analytic transition is compromised by its numerical instability and the violation of its own "fixed-prior" assumptions. Furthermore, the reported SOTA gains on PMO are an artifact of a 25x budget expansion rather than algorithmic superiority.
