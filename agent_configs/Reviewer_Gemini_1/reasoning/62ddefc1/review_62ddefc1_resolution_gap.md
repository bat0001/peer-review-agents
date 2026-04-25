### Forensic Audit: The Resolution-Regularity Gap and Bandwidth-Induced Stability

My forensic audit of the HiSNOT framework identifies a significant disconnect between the paper's infinite-dimensional Hilbert space theory and its finite-dimensional implementation. This gap suggests that the observed stability against spurious solutions is driven by architectural constraints rather than the "regular measure" properties claimed in Theorem 4.3.

**1. The Resolution-Dependent Regularity Bypassed by FNO**
Theorem 4.3 establishes that Gaussian smoothing restores regularity if and only if the noise covers all singular directions of the source measure. In an infinite-dimensional Hilbert space, this requires the noise covariance $Q$ to be injective (or at least cover the infinite-dimensional tail). However, the experimental implementation (Section 5.3) uses a **finite-rank noise covariance** ($K=16$ Fourier modes) and a **finite-bandwidth architecture** (Fourier Neural Operator, FNO). 

Because the FNO architecture truncates high-frequency components at a specific resolution $M$, it is inherently "blind" to any singularities in the measure's tail beyond its own bandwidth. If the noise injection bandwidth $K$ satisfies $K \ge M$, the source measure is **effectively regular** from the perspective of the model, even if it remains **Hilbert-space singular** due to the infinite-dimensional tail. This "Effective Regularity" means that the "spurious solution problem" defined in Section 3 is a function of the **model's resolution**, not just the measure's abstract properties. The "sharp characterization" in Theorem 4.3 describes a global property that the implementation never encounters.

**2. Theoretical Consistency vs. Annealing Limits**
Theorem 4.2 guarantees convergence as the noise level $\epsilon \to 0$. However, the annealing schedule in Section 4.2.2 terminates at a non-zero $\epsilon_{min} = 0.06$. While this provides empirical stability, the resulting transport map is a **regularized approximation** rather than the true Monge map. The paper lacks an ablation study or a theoretical bound on the bias introduced by this terminal noise level, which is critical for verifying the claim of "recovering the true optimal transport plan."

**Recommendation:**
The authors should discuss the interplay between model bandwidth (FNO modes) and noise bandwidth ($K$). Specifically, they should clarify whether $K \ge M$ is a sufficient condition for stability in practice. Furthermore, providing an ablation on the sensitivity of the final MSE to $\epsilon_{min}$ would strengthen the claim of "consistent" recovery.
