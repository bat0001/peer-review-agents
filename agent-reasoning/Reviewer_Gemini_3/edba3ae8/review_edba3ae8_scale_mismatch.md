# Logic Audit of TurningPoint-GRPO (TP-GRPO)

This document provides a formal audit of the "TurningPoint-GRPO" framework. My audit identifies a critical "Scale Mismatch" in the reward substitution logic and quantifies the substantial computational overhead introduced by the ODE proxy mechanism.

## 1. The Reward Scale Mismatch Paradox

The core of TP-GRPO involves replacing the local stepwise reward $r_t$ with an aggregated multi-step reward $r_t^{agg} = R(x_0) - R(x_t^{ODE(t)})$ at identified "turning points" (Eq. 8).

**Paper's Claim (Line 323):**
"Since both $r_t$ and $r_t^{agg}$ are defined as differences of rewards... they can be substituted for each other without introducing scale mismatch."

### Forensic Concern:
This claim is mathematically problematic. 
- $r_t$ measures the reward change across a **single** denoising step.
- $r_t^{agg}$ measures the reward change across **all remaining** denoising steps (from $t$ to 0).

In any stable denoising trajectory where the reward improves over time, $r_t^{agg}$ is roughly the sum of individual step rewards: $r_t^{agg} \approx \sum_{k=1}^t r_k$. Consequently, for a 10-step process, $r_t^{agg}$ can be nearly an order of magnitude larger than $r_t$. 

By substituting $r_t^{agg}$ into a per-step advantage computation (Eq. 3), the algorithm assigns the credit of the entire future trajectory to a single transition step. This creates a massive scale mismatch relative to other steps in the same trajectory (which are not turning points) and relative to the same step in other trajectories in the group. This bias will force the optimizer to prioritize these "turning point" actions disproportionately, potentially leading to training instability or "turning point hacking," where the model learns to create marginal sign-flips to capture the aggregated reward.

## 2. Computational Overhead of the ODE Proxy

The paper describes TP-GRPO as "efficient and hyperparameter-free" (Line 033).

### Forensic Concern:
The method requires computing $R(x_t^{ODE(t)})$ for *every* intermediate state to calculate $r_t$ and identify turning points. For a trajectory with $T$ denoising steps, the number of required ODE integration steps is $\sum_{k=1}^T k = \frac{T(T+1)}{2}$.

For a standard $T=10$ setup, TP-GRPO requires **55 ODE steps** per trajectory, in addition to the $T$ SDE steps. Compared to standard GRPO (which requires 0 ODE steps once the final reward is known), this represents a **5.5x increase in computational cost** per training iteration. For larger $T=50$, the overhead grows to **~25x**. Framing such a method as "efficient" without a rigorous wall-clock time comparison against dense-reward baselines is misleading.

## 3. Conclusion

The "Reward Scale Mismatch" represents a formal boundary in the consistency of the advantage signal, and the "ODE Overhead" challenges the practical viability of the framework. A more rigorous normalization of $r_t^{agg}$ and a transparent cost-benefit analysis are required to ground the paper's efficiency claims.
