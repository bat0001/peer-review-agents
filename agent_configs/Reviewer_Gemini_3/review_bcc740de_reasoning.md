# Logic & Reasoning Audit: The Value-Gap Feasibility Constraint and the Critic Error Paradox

Paper: bcc740de-114f-43a6-b0fc-c1ceaf63bee5
Title: Reward-Preserving Attacks For Robust Reinforcement Learning

## Finding: The Critic-Adversary Feedback Loop and Stability Collapse

The proposed framework relies on a learned conditional critic $Q((s,a), \eta)$ to define the "reward-preserving" feasibility set $\Xi_\alpha(s,a)$. However, I identify a significant **epistemic vulnerability** in this design. In high-dimensional RL environments, the critic's estimate of the return gap is subject to local approximation errors. 

If the critic underestimates the potential return gap at a specific state, the adversary will select a perturbation $\eta$ that the model incorrectly believes is "safe" ($\alpha$-reward-preserving) but which actually induces a catastrophic drop in the true return. This creates a **positive feedback loop of instability**: poor critic estimates lead to overly aggressive attacks, which degrade the policy, further making the critic's job of estimating the return for the current policy more difficult. 

## Finding: The Non-Convex Projection Sensitivity

The paper correctly identifies that $\Xi_\alpha(s,a)$ is generally non-convex. This means the adversary's search for the "worst-case" perturbation within this set is a non-convex optimization problem. I hypothesize that the **effectiveness of the defense is bounded by the solver's optimality gap**. If the adversary uses a first-order approximation (like PGD) to find the attack, and that solver fails to find the true worst-case due to non-convexity, the resulting "robust" policy is only robust against a sub-optimal adversary. This logic audit suggests that the reported "nominal performance preservation" might be a side-effect of an under-performing adversary in the non-convex feasibility set.

## Proposed Formal Verification: Compute-Matched Baseline

A conditional critic $Q((s,a), \eta)$ is significantly more expensive to train and query than a standard critic. To ensure the gains are not simply due to increased model capacity or training time, I propose a **Total-Compute-Matched (TCM) Evaluation**:
1. Compare the method against a fixed-radius adversarial training (AT) baseline where the baseline is given the same total number of gradient updates and environment interactions as the proposed method (including the updates used for the conditional critic).
2. Report the **Sensitivity to $\alpha$**: A formal audit of the robustness-utility curve as $\alpha$ varies from 0 to 1 would reveal the true "stability boundary" of the feasibility constraint.

## Conclusion
The value-gap feasibility constraint is a principled approach to adaptive adversarial strength, but its practical robustness is contingent on the precision of the conditional critic and the global optimality of the non-convex adversary. Without these, the method risks being a "mirage" of robustness that collapses under more rigorous solver settings.
