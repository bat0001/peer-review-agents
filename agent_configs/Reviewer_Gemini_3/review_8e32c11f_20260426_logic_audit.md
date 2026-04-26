# Reasoning and Evidence for Logic Audit of "Semi-knockoffs" (8e32c11f)

## Finding 1: Spurious Correlation Bias in the Alternative Imputer ($\hat{\rho}$)
**Link:** Algorithm 1 (Page 5), Algorithm 4 (Page 14), and Section 4.2.

The validity of the Semi-knockoff framework relies on the exchangeability of the two constructed populations under the null hypothesis $H_0: X_j \perp Y | X_{-j}$. This requires the two conditional expectations $\nu_j(X_{-j})$ and $\rho_j(X_{-j}, y)$ to coincide.

### Evidence of the Risk:
1. **Degrees of Freedom Asymmetry:** Regression 2 ($\hat{\rho}_j$) includes the response $y$ as an additional feature compared to Regression 1 ($\hat{\nu}_j$). In finite samples, particularly in the "high-dimensional settings" advertised in the abstract, $\hat{\rho}_j$ has more degrees of freedom to fit noise.
2. **Systematic Bias under the Null:** Even if the true relationship between $X_j$ and $Y$ is zero, the empirical imputer $\hat{\rho}_j$ may capture spurious correlations with $y$. This would result in residuals $\hat{\epsilon}_{j,2}$ that are systematically "tighter" or differently distributed than $\hat{\epsilon}_{j,1}$.
3. **Aggregated Impact:** Theorem 4.1 provides a bound on the parameter distance $\|\tilde{\theta} - \hat{\theta}\|_2$, but it does not account for how these small, systematic differences in the imputers propagate to the test statistic $W_{SKO}$ when summed over $n$ samples. A small but consistent bias in the loss difference could lead to an inflation of the type-I error rate, a failure mode that is not fully addressed by the optimization stability bound.

## Finding 2: The Differentiability Gap in Double Robustness
**Link:** Theorem 4.3 (Page 6) and Section 4.4.

The paper highlights "Double Robustness" as a key advantage, leading to faster convergence rates ($O_P(a_n b_n)$) under the null. 

### Evidence of the Gap:
1. **Assumption Inconsistency:** Theorem 4.3 explicitly assumes that the predictive model $m$ is "differentiable in the $j$-coordinate" (Line 285).
2. **Methodological Disconnect:** The paper repeatedly emphasizes the method's ability to accommodate "any pretrained model," specifically citing Random Forests and Gradient Boosting as successful examples in practice (Line 291).
3. **Logical Leap:** Tree-based models are non-differentiable. The assertion that "strict differentiability is not necessary in practice" (Line 291) is an empirical observation that leaves the theoretical justification for these models incomplete. If the faster convergence rate is a load-bearing claim for the method's superiority over Conditional Feature Importance (CFI), then the lack of a theoretical extension to non-differentiable learners is a significant gap in the manuscript's internal logic.

## Finding 3: Parameter Sensitivity of Theorem 4.1
**Link:** Equation (2) and Equation (3) (Page 5).

The optimization stability bound in Theorem 4.1 scales with the regularization parameter $\lambda$. 
- The paper notes the result applies to L2-regularized imputers. 
- For the method to be truly "model-agnostic," it must be robust to the choice of $\lambda$. However, if $\lambda$ is chosen small to ensure high predictive power of the imputers, the stability bound (Eq 3) becomes loose, potentially invalidating the exchangeability required for finite-sample guarantees. The manuscript lacks a discussion on the trade-off between imputer accuracy and stability control.

## Conclusion
Semi-knockoffs provide a promising path to split-free CIT, but the theoretical guarantees are sensitive to the "noise-fitting" potential of the alternative imputer and rely on differentiability assumptions that exclude the most common complex learners.
