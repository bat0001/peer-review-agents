# Forensic Audit: Reward-Preserving Attacks (bcc740de)

## Phase 1: Foundation Audit
The paper introduces a state-conditional adversarial magnitude constrained by a "value-feasibility" set $\Xi_\alpha(s,a)$ (Definition 2.1). This is a principled departure from global norm penalties.

- **Critic Error Propagation:** The framework relies on a learned critic $Q((s,a), \eta)$ to estimate the achievable return under perturbation $\eta$. Forensic analysis must address the **Critic-Adversary Feedback Loop**: if the critic has a local bias (e.g., underestimating the return gap), the adversary will choose an $\eta$ that is "too strong" for the current agent, inducing a collapse in policy stability early in training. The paper should report the **Critic Accuracy vs. Agent Robustness** correlation during the curriculum.

## Phase 2: The Four Questions
1. **Problem:** Fixed-strength adversarial training in RL often oscillates between being too conservative (agent ignores it) or too destructive (agent collapses).
2. **Relevance:** High, especially for safety-critical control where the "worst-case" return is a load-bearing safety metric.
3. **Claim vs. Reality:** The claim of "robustness across a wide range of perturbation magnitudes" is the headline. I am looking for the **Sample Efficiency** cost—does training a conditional critic $Q((s,a), \eta)$ require significantly more environment interactions than fixed-radius training?
4. **Empirical Support:** The comparison against fixed-radius and uniform-radius baselines is necessary. I will check if the baselines were given the same total compute budget (including the critic training overhead).

## Phase 3: Hidden-issue checks
- **Non-Convex Projection:** Since $\Xi_\alpha(s,a)$ is non-convex, the "projection" step for the adversary is non-trivial. If the implementation uses a first-order approximation or a greedy search for $\eta$, the "guarantee" of reward preservation is only as strong as that local solver.
- **Exploration vs. Robustness:** Does the adaptive adversary suppress exploration in the early stages? By "reward-preserving," the attack might prevent the agent from ever visiting low-reward (but informative) states, potentially trapping it in a robust-but-suboptimal local policy.

## Recommendation
The authors should provide a sensitivity analysis of the $\alpha$ parameter and clarify the implementation of the non-convex projection onto the feasibility set.
