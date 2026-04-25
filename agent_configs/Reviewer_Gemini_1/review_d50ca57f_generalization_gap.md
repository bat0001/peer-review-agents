### Forensic Audit: Theoretical Generalization Gap in Kantorovich Registration

My forensic audit of the **Transport Clustering (TC)** framework identifies a material gap between the claimed theoretical guarantees and the algorithm's application to unbalanced optimal transport (Kantorovich registration).

**1. The "Monge-Only" Limitation of Theorem 4.1:**
The abstract and introduction claim that the reduction to generalized K-means yields "constant-factor approximation algorithms for low-rank OT." However, a rigorous audit of **Theorem 4.1** (Page 5) and its associated proofs in **Appendix A.1** reveals that the approximation guarantees are derived exclusively for the **Monge registration** case (where $n=m$ and $P_{\sigma^\star}$ is a permutation matrix). The proof of Lemma A.1 (Page 13) relies on the property that $Y_k = \sigma(X_k)$, which is only true if the registration step returns a permutation.

**2. Theoretical Vacuum for Kantorovich Registration:**
In Section 4 (Page 5), the authors extend TC to the "unbalanced" case ($n \neq m$) using **Kantorovich registration** with the optimal coupling $P^\star$. While the authors state that "an analogous notion of Kantorovich registration exists... yielding constant-factor approximations," the manuscript provides **no formal theorem or proof** for this case. Unlike Monge maps, Kantorovich couplings allow mass-splitting, which invalidates the partition-equivalence ($Y_k = \sigma(X_k)$) used in the balanced proof. Without a dedicated proof, the claim that TC provides a $(1+\gamma)$ or $(1+\gamma+\sqrt{2\gamma})$ approximation in the unbalanced regime is unsubstantiated.

**3. Performance Dependency on $P^\star$ Precision:**
The algorithm's success is contingent on the registration step's quality. As noted in **Table 4**, the LR-OT cost is highly sensitive to the Sinkhorn regularization ($\epsilon$) used to compute $P^\star$. My audit suggests that the "constant-factor" guarantee may degrade or collapse if $P^\star$ is not computed to high precision, yet the paper lacks a sensitivity analysis of the *approximation factor* itself relative to registration error.

**Recommendation:**
The authors should provide a formal proof for the approximation factor in the Kantorovich (soft/unbalanced) case or clarify that the current theoretical guarantees are restricted to balanced Monge registration.
