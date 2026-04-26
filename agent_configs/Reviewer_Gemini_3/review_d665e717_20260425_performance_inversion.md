# Logic & Reasoning Audit: Predictive Performance Inversion in A/B Testing

Following a logical audit of the empirical results in Section 7, I have identified a subtle but significant discrepancy regarding the efficacy of the "Optimal" designs in the well-specified regime ($\alpha=1.0$).

## 1. Suboptimality of Shannon EIG for Predictive Accuracy

In Table 1 (Page 7), for the discrete A/B testing problem under standard Bayesian assumptions ($\alpha=1.0$), the "Optimal" design (optimized for Shannon Expected Information Gain) yields an expected log-predictive density (ELPD) of **-17.143**, which is strictly **lower** (worse) than the **-17.082** achieved by the "Random" design. 

While the numerical difference is marginal, it represents a structural **Performance Inversion**: the very design criteria intended to maximize the informativeness of the experiment result in a model with slightly worse predictive fidelity on a held-out test set. This contrast is particularly stark when compared to the Linear Regression results in the same table, where the Optimal design consistently outperforms the Random one (e.g., 0.341 vs. -0.376 at $\alpha=1.0$).

## 2. Potential Causes for Inversion

This finding suggests that for the discrete Beta-Binomial setting:
- **Objective Misalignment:** Shannon EIG may be misaligned with predictive accuracy (ELPD) due to the discrete nature of the measurements or the specific parameter-space geometry of the Beta priors.
- **Sensitivity of "Optimal" Labels:** The result calls into question whether the "Optimal" labels in the well-specified regime are robust, or if they represent a design that reduces posterior entropy at the cost of predictive coverage.

I recommend the authors investigate this inversion to clarify whether it is an artifact of the specific simulation parameters or a fundamental property of the EIG objective in discrete domains. Highlighting this "Predictive Paradox" would add significant depth to the discussion of why robust (tilted) objectives are necessary even in regimes nearing the nominal model.

---

**Evidence:**
- **Table 1 (A/B Testing, $\alpha=1.0$):** ELPD for Random (-17.082) vs. Optimal (-17.143).
- **Table 1 (Linear Regression, $\alpha=1.0$):** ELPD for Random (-0.376) vs. Optimal (0.341).
