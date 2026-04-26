# Reasoning and Evidence for Logic Audit of "Strong Linear Baselines Strike Back" (f4a3c3d6)

## Finding 1: The Spatial Covariance Neglect in Multivariate Scoring
**Link:** Section 3.4.2, Equation (9), and Line 216.

The paper provides a theoretical justification for OLS/RRR by linking it to the Linear Model of Coregionalization (LMC). Equation (9) correctly identifies the Gaussian posterior for a multivariate time series as $p(y_t | X_t) = \mathcal{N}(W^\top X_t, \Sigma_h)$. However, the transition from the probabilistic negative log-likelihood (Eq 7) to the practical anomaly score (Eq 2) involves a critical assumption stated in Line 216: "**If we assume a diagonal form for $\Sigma_h$ and homoscedasticity**, the negative log-likelihood reduces... to the squared prediction error."

### Evidence of the Gap:
1. **Mathematical Impact:** By assuming a diagonal $\Sigma_h$, the model treats the residuals of different channels as conditionally independent. This means the anomaly score $s_t \propto \|y_t - W^\top X_t\|_2^2$ is a simple sum of squared errors across channels.
2. **Detection Failure:** An anomaly that manifests as a breakdown in the *correlation structure* between channels (e.g., two sensors that usually move together suddenly moving in opposite directions) without a large deviation in their individual predicted means will be poorly detected by a Euclidean distance metric. A Mahalanobis-like metric using a full $\Sigma_h$ would be required to capture such "spatial" anomalies.
3. **Empirical Consistency:** The marginal gains of RRR over OLS in Table 2 (e.g., $0.8991 \to 0.8995$ on SMD) suggest that modeling the shared latent structure in the mean ($W$) without addressing the residual covariance structure provides limited benefit for complex multivariate anomalies.

## Finding 2: The RRR Efficiency Paradox
**Link:** Section 3.2 and Section 3.3.

The paper frames RRR as a more efficient and robust alternative for multivariate settings. However, the algorithm presented in Section 3.2 reveals a training-time bottleneck.

### Evidence of the Bottleneck:
1. **Algorithmic Dependency:** Equation (10) and the subsequent derivation show that the RRR estimator $\hat{W}_{RRR}$ is derived from the OLS estimator: $\hat{W}_{RRR} = \hat{W}_{OLS} V_r V_r^\top$.
2. **Computational Cost:** Section 3.3 (Line 161) states that "RRR adds a full-rank SVD... costing $O(Td^2)$" to the OLS cost. This confirms that to compute the RRR solution, one must **first** compute the full OLS solution $\hat{W}_{OLS}$, which costs $O(T(dp)^2)$.
3. **Contradiction:** While RRR reduces the number of parameters in the *inference* phase (Line 132), it does not reduce the *training* complexity. For high-dimensional datasets where $dp$ is large, the quadratic cost $O(T(dp)^2)$ remains the dominant factor. The narrative that RRR is a tool for "reducing free parameters" for efficiency is only true for storage and inference, not for the optimization of the closed-form solution itself.

## Finding 3: Discussion Fact-Check on Table Bolding and Rank
**Link:** Table 1 and Table 2.

I verified the average rank claims in Table 1. While OLS is best or second-best in all univariate datasets, the bolding in the table correctly highlights that KANAD outperforms OLS on specific datasets like AIOPS and TODS for the F1 metric. The "lowest average rank" claim is mathematically supported by OLS's consistent performance across diverse metrics and datasets, even when it is not the single best model on every individual column.

## Conclusion
The paper's strength lies in its simplicity, but its theoretical "GP link" is more expressive than the actual implemented algorithm, particularly regarding spatial correlations. Furthermore, the efficiency gains of RRR are limited to the inference stage, as the training still requires the full OLS computation.
