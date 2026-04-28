# Reasoning: Covariance Bias in Pilot-Guided Intervention Safety

This file documents the formal logical derivation of the **Covariance Bias** in the pilot-based success estimator proposed in "Accurate Failure Prediction in Agents Does Not Imply Effective Failure Prevention."

## 1. The Pilot Estimator
The paper proposes a pre-deployment pilot test to estimate the success delta $\Delta S$:
$$\Delta \hat{S} = \hat{p}\hat{r} - (1-\hat{p})\hat{d}$$
where:
- $\hat{p}$ is the empirical probability that the critic is correct.
- $\hat{r}$ is the empirical recovery rate on flagged samples.
- $\hat{d}$ is the empirical disruption rate on incorrectly flagged samples.

This estimator treats $p, r, d$ as scalar parameters of the system.

## 2. Formal Decomposition of the Expected Impact
In reality, $p, r, d$ are not constants but random variables dependent on the specific task instance $x$. Let $I_x \in \{0, 1\}$ be the indicator that the critic is correct for task $x$, $R_x \in \{0, 1\}$ be the indicator of recovery if flagged, and $D_x \in \{0, 1\}$ be the indicator of disruption if incorrectly flagged.

The true expected impact $E[\Delta S]$ over the task distribution is:
$$E[\Delta S] = E[I_x R_x - (1-I_x) D_x]$$

Using the definition of covariance $E[AB] = E[A]E[B] + Cov(A, B)$:
$$E[I R] = E[I]E[R] + Cov(I, R)$$
$$E[(1-I) D] = E[1-I]E[D] + Cov(1-I, D) = E[1-I]E[D] - Cov(I, D)$$

Substituting these into the expectation:
$$E[\Delta S] = \bar{p}\bar{r} - (1-\bar{p})\bar{d} + [Cov(I, R) + Cov(I, D)]$$
where $\bar{p}, \bar{r}, \bar{d}$ are the population means.

## 3. Identification of the Bias
The pilot estimator $\Delta \hat{S}$ converges to the product of means $\bar{p}\bar{r} - (1-\bar{p})\bar{d}$. Therefore, the **Pilot Bias** is exactly:
$$\text{Bias} = -[Cov(I, R) + Cov(I, D)]$$

## 4. Logical Implications
- **Epistemic Pessimism ($Cov(I, R) < 0$):** In shared-knowledge systems, the critic is most likely to be correct ($I=1$) on failures that stem from fundamental gaps in the underlying model. These are precisely the failures where the agent's recovery probability $R$ is lowest. A negative covariance here means the pilot test overestimates recovery.
- **Fragility Sensitivity ($Cov(I, D) > 0$):** False positives $(1-I=1)$ are most likely on "boundary" cases where the trajectory is successful but atypical. These successful-yet-atypical trajectories are logically more fragile ($D=1$) than "canonical" successful ones. A positive covariance here means the pilot test underestimates disruption.

## Conclusion
Even if the pilot set is "on-domain," the mean-based estimator is logically blind to the **instance-level correlation** between critic accuracy and agent fragility. The pilot test provides an upper bound of utility, not a realistic expectation, unless the covariance terms are explicitly measured or bounded.
