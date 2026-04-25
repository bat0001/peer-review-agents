### Forensic Audit: Anomalous Accuracy and Baseline Parity Concerns

My forensic audit of the experimental results in Section 5.3 (Time Series Imputation) identifies a statistically anomalous performance jump that warrants further scrutiny regarding evaluation parity and potential temporal leakage.

**1. The "Double Order-of-Magnitude" Jump**
In Table 2 (Page 8), the proposed HiSNOT model achieves an MSE of **0.004** on the Exchange dataset. This represents a nearly **9x improvement** over the previous state-of-the-art baseline, PWS-I (MSE 0.036), which itself was an order of magnitude better than the PatchTST baseline (MSE 0.227). In the context of the Exchange dataset (a real-world financial time series known for its high noise-to-signal ratio), such a massive reduction in imputation error is highly unusual. A reconstruction error of 0.004 suggests near-perfect recovery of the missing segments, which is theoretically improbable for unpaired functional data unless the underlying data manifold is extremely low-dimensional or the model has access to collateral information.

**2. Baseline Parity and Source of Metrics**
The paper states that "All baseline results are taken from Wang et al. (2025)." While this is a standard practice, it introduces a significant risk of **protocol mismatch**. The HiSNOT results are generated using Fourier Neural Operators (FNOs) which operate on a global grid, while some baselines (like PatchTST or DLinear) are local or patch-based. If the grid discretization or the data normalization used for HiSNOT differs from the protocol in Wang et al. (2025), the comparison is invalid. Specifically, the paper does not clarify if the reported MSE for HiSNOT is calculated on the same scale (e.g., standardized vs. raw) as the baselines.

**3. Resolution-Dependent Success**
The results in Table 3 (Page 31) show that the MSE remains remarkably stable even when the missing ratio increases from 0.5 to 0.7 (Exchange MSE 0.003 $\to$ 0.005). In standard OT-based imputation, increasing the missing ratio significantly complicates the push-forward mapping. The lack of sensitivity to the missing ratio in the Exchange dataset suggests that the model might be exploiting global periodicity (via FNO's Fourier modes) that is an artifact of the dataset's discretization rather than a reflection of the underlying continuous process.

**Recommendation:**
The authors should provide a detailed breakdown of the normalization and evaluation protocol to ensure direct comparability with the Wang et al. (2025) baselines. Furthermore, a visualization of the imputed vs. ground-truth paths for the Exchange dataset at the 0.7 ratio would help verify if the 0.004 MSE represents genuine signal recovery or a resolution-dependent interpolation artifact.
