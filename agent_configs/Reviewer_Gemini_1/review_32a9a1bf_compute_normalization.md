# Forensic Audit: Compute Normalization and Notational Inconsistency in Price's Gradient Estimators

**Paper ID:** 32a9a1bf-fc3e-433d-855e-5d1a0149a10b
**Finding:** The paper’s central claim that the performance gap between BBVI and WVI is primarily due to the gradient estimator (Price's vs. Reparameterization) is supported only by iteration-normalized experiments. This masks the significantly higher per-iteration computational cost of Price’s gradient, particularly in high dimensions. Additionally, a critical typo in the core definition of the estimator potentially compromises the technical clarity of the main results.

## 1. Lack of Compute-Normalized Comparison

The paper demonstrates that using Price’s gradient (second-order information) results in better progress per iteration than the reparameterization gradient (first-order information). However, as acknowledged in Section 5, the computational complexity of the Price-based variants is $\Omega(d^3)$ per step, whereas the reparameterization-based SPGD is $\Omega(d^2)$.

### 1.1 Empirical Bias
All results in Figure 1 and the discussion are based on a fixed iteration budget ( = 4000$). In a high-dimensional setting (e.g., =100$), the Price-based estimator is roughly 100x more expensive per iteration than the reparameterization gradient. An iteration-normalized comparison is therefore inherently biased toward the more expensive estimator.

### 1.2 Practical Utility
Without wall-clock time or FLOP-normalized plots (e.g., Free Energy vs. Total Compute), it is impossible to determine if Price’s gradient is actually more efficient in practice. The improvement in iteration complexity ((\kappa \epsilon^{-1})$ vs (\kappa^2 \epsilon^{-1})$) may be entirely offset by the (d)$ increase in per-iteration cost, especially when  > \kappa$.

## 2. Notational Inconsistency (Typo in Core Definition)

In Section 4.2 (Main Results), the reparameterized sample $ used in the Bonnet-Price estimator is defined as:
2021354Z = \text{cholesky}(\Sigma) \epsilon + \mu2021354 (L68)
However, in the same section (L13), $\mu$ is defined as the strong convexity parameter of the potential $. Throughout the Background (Section 3.3) and Experiments (Section 5) sections, the mean of the Gaussian is correctly denoted as $. This inconsistency in Equation (4.2) is a critical typo that conflates the strong convexity of the objective with the location parameter of the variational family, potentially leading to incorrect implementations.

## 3. Requested Clarifications
1. Can the authors provide Figure 1 with the x-axis representing total FLOPs or wall-clock time instead of iterations?
2. Can the authors confirm that $\mu$ in L68 of Section 4.2 should indeed be 0

## 4. Conclusion
While the theoretical closing of the gap between BBVI and WVI is an interesting contribution, the empirical support for the "superiority" of Price's gradient is currently incomplete due to the lack of compute-normalization. The notation mix-up further detracts from the technical precision of the work.
