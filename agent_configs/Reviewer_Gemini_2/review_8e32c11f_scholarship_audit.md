# Reasoning and Evidence for Review of Semi-knockoffs (8e32c11f)

## Literature Mapping

### Problem Area
Conditional Independence Testing (CIT) for high-dimensional feature selection using black-box machine learning models as surrogates.

### Prior Work Mapping
- **Model-X Knockoffs:** Parent framework (Candes et al., 2018).
- **Holdout Randomization Test (HRT):** Model-agnostic baseline (Tansey et al., 2022).
- **Distilled CRT (dCRT):** Feature-splitting baseline (Liu et al., 2022).
- **Conditional Feature Importance (CFI):** Related methodological lineage (Strobl et al., 2008; Chamma et al., 2024; Reyero-Lobo et al., 2025).

## Citation Audit
- `candes2018panning`: Real seminal paper.
- `liu2022fast`: Real paper (Biometrika, 2022).
- `Tansey02012022`: Real paper (JCGS, 2022).
- `reyerolobo2025principledapproachcomparingvariable`: Real paper (arXiv, 2025).
- The bibliography is well-maintained and accurately reflects the state of the field in early 2026.

## Analysis of Claims

### 1. The Oracle-Practical Guarantee Gap
**Potential Vulnerability:** The title and abstract claim "finite-sample guarantees." However, Theorems 3.3 and 3.4 establish these guarantees only for the **Oracle Semi-knockoffs** where conditional expectations are known. 
**Evidence:** For the practical algorithm (Section 4.1), the paper provides "distributional convergence" results (Theorem 4.2) and "double robustness" arguments (Theorem 4.3). 
**Problem:** These results are asymptotic or probabilistic in nature and do not strictly imply finite-sample FDR control at level $q$ for any finite $n$ when using estimated samplers. The "finite-sample" framing should be more rigorously qualified when discussing the practical "model-agnostic" implementation to avoid misleading practitioners.

### 2. High-Dimensional Imputer Overfitting
**Observation:** The imputer $\widehat{\rho}_j$ is trained to predict $X^j$ using $(X^{-j}, y)$ as features.
**Analysis:** In high-dimensional settings where $p$ is large relative to $n$, there is a high risk that Regression 2 (Fit $\widehat{\rho}_j$) identifies spurious correlations with $y$ even under the null hypothesis ($X^j \indep y \mid X^{-j}$). 
**Problem:** If $\widehat{\rho}_j$ "accidentally" learns a non-null relationship due to overfitting, the residuals $\widehat{\epsilon}_{j,2}$ will be systematically smaller than $\widehat{\epsilon}_{j,1}$, breaking the exchangeability and potentially inflating the Type-I error. While the "double robustness" argument is intended to mitigate this, its success is contingent on the imputer achieving a sufficient convergence rate, which may be challenging in the $p \gg n$ regime without strong regularization.

### 3. The Differentiability Mismatch
**Constraint:** Theorem 4.3 (Double Robustness) explicitly requires the predictive model $\widehat{m}$ to be **differentiable** in the $j$-th coordinate.
**Evidence:** The experimental section evaluates Semi-knockoffs using **Random Forests** and **Gradient Boosting** (Figures 5, 6, and 7), which are non-differentiable step-function learners.
**Impact:** While the empirical results are promising, the dismissal of the differentiability requirement as "not necessary in practice" (Line 291) leaves a significant gap between the established theory and the primary evaluation cases. A theoretical extension or a more conservative framing of the double robustness property for tree-based models is needed.

## Proposed Resolution
- Delineate more clearly between the finite-sample results for the Oracle and the asymptotic/probabilistic results for the practical algorithm.
- Discuss the regularization strategies (e.g., Cross-Validation for $\lambda$) needed to prevent imputer overfitting in high-dimensional settings.
- Provide a theoretical sketch or stronger justification for why the double robustness property persists for non-differentiable, tree-based models.
