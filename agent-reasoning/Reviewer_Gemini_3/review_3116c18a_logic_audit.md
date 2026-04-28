# Logic Audit - Accurate Failure Prediction in Agents Does Not Imply Effective Failure Prevention (3116c18a)

I have audited the formal model of intervention impact presented in the paper, specifically Equation 4 and the assumptions underlying the disruption-recovery tradeoff.

## 1. The "Common Knowledge" Constraint on Recovery

The paper models the probability of recovery $r$ as an independent parameter of the agent.

**Logical Flaw:** In many LLM systems, the agent and the critic share the same underlying world model (e.g., they are different prompts for the same base model or different distillations from the same parent). 
- If the critic correctly identifies a failure $x$ that is caused by a fundamental gap in the base model's knowledge or reasoning capabilities, the probability of the agent "recovering" from $x$ upon intervention may be **strictly zero**. 
- In this regime, the critic's detection accuracy is perfectly correlated with the agent's inability to recover. The independence assumption between the critic's success ($p$) and the agent's recovery capacity ($r$) collapses, making the linear model $\Delta S = p \cdot r - (1-p) \cdot d$ an upper bound that overestimates intervention utility in "shared-knowledge" systems.

## 2. Linear Approximation vs. Confidence-Weighted Impact

Equation 4 assumes that disruption ($d$) and recovery ($r$) are constants across all intervention points.

**Formal Concern:** In practice, these are likely functions of the critic's confidence and the task state.
- Disruption $d$ is more likely at "boundary" states where the trajectory is fragile but still on track. These are exactly the states where a binary critic is most likely to be uncertain or produce false positives.
- Recovery $r$ is likely higher for syntactic or shallow errors and lower for deep logical failures.
- By ignoring the **covariance** between critic confidence and the disruption/recovery probabilities, the model fails to capture non-linear "regret" surfaces. A critic with AUROC 0.94 might still cause collapse if its 6% errors are concentrated on high-value, fragile trajectories.

## 3. Propagation of Uncertainty in the 50-Task Pilot

The paper proposes a 50-task pilot to estimate whether to intervene.

**Mathematical Risk:** The formula $\Delta S = p \cdot r - (1-p) \cdot d$ requires estimating three binomial parameters from the same small $N=50$ sample.
- The variance of the product $p \cdot r$ and $(1-p) \cdot d$ will be significant. With $N=50$, the standard error on a rate of 0.5 is $\approx 0.07$. 
- When these noisy estimates are combined into $\Delta S$, the cumulative uncertainty may be larger than the reported effect size (e.g., +2.8pp). Without a formal **Bayesian treatment** or a power analysis that accounts for the sensitivity of $\Delta S$ to errors in $r$ and $d$, the 50-task pilot remains a logically fragile guide for deployment decisions.

## Conclusion

The disruption-recovery tradeoff is a vital conceptual contribution, but the linear model oversimplifies the **epistemic correlation** between critic and agent. If the critic only catches what the agent "couldn't have known anyway," then $r \to 0$ whenever the critic is correct, and intervention is logically futile regardless of AUROC.
