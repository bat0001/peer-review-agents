# Logic Audit - Statsformer (24c0bbef)

## 1. Complexity-Accuracy Trade-off in the Model Library (Theorem 1)

Theorem 1 establishes an oracle-style guarantee that the Statsformer ensemble competes with the best convex combination of its $L$ candidate learners.

**Logical Concern:** The bound for convex aggregation typically scales with $\sqrt{\frac{\log L}{n}}$, where $L$ is the size of the library and $n$ is the number of samples.
- In Statsformer, $L = M \times |\mathcal{H}|$, where $M$ is the number of base learners (Lasso, XGBoost, etc.) and $|\mathcal{H}|$ is the grid size of prior hyperparameters $(\alpha, \beta)$.
- If a practitioner uses a fine grid to "search" for the best prior influence, $L$ increases.
- While the "Super Learner" framing suggests that adding more candidates "cannot hurt" the oracle performance, it **can** hurt the finite-sample performance by increasing the estimation error of the stacking weights.
- **Audit Finding:** The paper uses a very small grid ($\alpha \in \{0, 1, 2\}$, $\beta \in \{0.75, 1\}$), resulting in a small $L$. This protects the finite-sample stability but limits the "adaptivity" to the prior. If the LLM prior requires a different scaling (e.g., $\alpha = 10$), the current library will not find it. If the library is expanded to find it, the "guardrail" efficiency of the stacking degrades.

## 2. Independence of Prior and Data (Algorithm 1)

The framework assumes the LLM prior $V$ is "independent" of the specific training set $D$ (elicited only from feature/target semantics).

**Mathematical Risk:** If the LLM was trained on the same benchmark datasets (e.g., GermanCredit, Bank Marketing), the prior $V$ is not a "semantic prior" but a "leaked posterior" from the LLM's training data.
- In this case, the stacking weights $\pi$ are not validating a "reasoning bias" but are instead performing a form of **ensemble meta-learning on leaked labels**.
- This would inflate the perceived performance of the "semantic prior" relative to the "no-prior" baseline.
- **Suggested Verification:** The paper's "Adversarial Prior" test (Section 6) uses inverted scores. A more rigorous test for "semantic vs. memory" would be to use **synthetic feature names** (e.g., "Feature_1", "Feature_2") and see if the performance drops to the no-prior baseline. If the method requires meaningful names, it is susceptible to "benchmark memorization" bias which is not addressed in the "safe prior" theory.

## 3. Stacking Weight Identifiability

The out-of-fold (OOF) stacking minimizes a proper loss (e.g., MSE or LogLoss) over the simplex $\Delta_L$.

**Logical Gap:** If multiple prior-modulated learners are highly correlated (e.g., $\alpha=1$ and $\alpha=1.1$ produce similar rankings), the stacking weights $\pi$ become non-identifiable.
- While this doesn't hurt the oracle *prediction* error, it makes the "calibration of influence" (interpreting which prior is "best") unstable.
- The paper claims the method "automatically downweights" bad priors. However, if a bad prior is correlated with a good one, it might receive non-zero weight, leading to a "false discovery" of semantic relevance.
- I recommend a **sparsity-inducing constraint** (e.g., $\ell_1$ penalty) on the stacking weights if the goal is to "detect" the most valid semantic prior, rather than just minimizing prediction error.

## Conclusion

Statsformer is a sound application of aggregation theory to the "LLM-as-prior" problem. However, the reliance on a small, fixed library $L$ and the potential for "semantic leakage" from benchmarks are critical factors that bound the generality of the "provable safety" claim.
