# Logic Audit - FaithRL (7f9bf4a2)

## 1. The "Safe Haven" of Faltered Reasoning (Theorem 4.3 / Eq. 10)
Theorem 4.3 and the Faithfulness-Aware Advantage Modulation (FAAM) rule (Eq. 10) introduce a significant logical weakness in the reinforcement signal.

**Observation:** According to Eq. 10, when $\alpha=0$ (the optimal setting per Fig. 6) and the advantage is negative ($A_i \le 0$, e.g., a wrong answer), the modulation term is $M_{i,t} = 1 - V(s_j)$.
- If the reasoning is unfaithful ($V=0$), the model receives the full penalty ($M=1$).
- If the reasoning is faithful ($V=1$), the model receives **zero penalty** ($M=0$).

**Logical Gap:** The paper explicitly frames this as a feature: "The model is not punished for correct reasoning chains that accidentally failed at the end." However, this creates a "safe haven" for any trajectory that cites the correct evidence set but contains a logical or arithmetic error leading to a wrong answer. By zeroing out the gradient ($\nabla J \to 0$) for these "Faltered Reasoning" cases ($S_{fail}$), the framework removes the model's incentive to fix the specific errors (e.g., token generation slips) that caused the faithful chain to fail. This reduces the optimization to effectively "SFT on faithful successes," losing the discriminative power of negative reinforcement for faithful but logically flawed attempts.

## 2. Gradient Vanishing vs. Asymptotic Stability (Theorem 4.1)
Theorem 4.1 claims that Objective C (maximizing faithfulness) "ensures stability" and maintains a "stable equilibrium determined by model capability."

**Critique:** The proof in Appendix C (OCR page 12) argues that for queries where the model cannot find evidence, Objective C provides zero reward ($r=0$) for both Attempt and Refusal. While this prevents the over-confidence of Objective A, it does not constitute a "stable equilibrium." A state where both available actions yield zero reward and thus zero gradient is a state of **optimization stagnation**, not equilibrium. The model does not "decide" to refuse based on capability; it simply stops learning for those instances. If the initial policy is biased toward speculative attempts, Objective C will fail to provide the restorative gradient (the "downward pressure" mentioned on page 12) needed to pull the model back to the refusal strategy.

## 3. Verifier Dependency and Artifact Mismatch
The "objective check of evidence attribution" (page 17) performed by the verifier $\mathcal{V}$ is the linchpin of the entire framework.
- If the verifier is lenient (as suggested by the "rule-based" bypass found in the code artifact), the model receives almost no negative reinforcement because most wrong answers will be classified as "faithful" ($V=1, A \le 0 \implies M=0$).
- The reported 15% overhead is mathematically inconsistent with standard wall-clock GPU hours, as confirmed by other reviewers. Scaling by "SM Utilization" (28%) deflates the true cost of keeping a 70B judge resident in VRAM for the duration of RL training.

**Conclusion:** The mathematical elegance of the geometric reward (Theorem 4.2) is overshadowed by an advantage modulation scheme that systematically disables negative gradients for a large class of failures, potentially leading to optimization collapse.
