# Forensic Audit: Why Depth Matters in Parallelizable Sequence Models (230fcebb)

## 1. Foundation Audit: Citation & Code Match
- **Citation Audit**: Bibliography is well-curated, referencing recent SOTA (*Merrill et al. 2024*, *Liu et al. 2022*).
- **Code Match**: **Material Theoretical Gap.** A static audit of the repository (`https://github.com/kazuki-irie/lie-algebra-state-tracking`) confirms it contains full training pipelines but **zero Lie-algebraic analysis code**. There is no implementation of the Magnus expansion terms, commutator mass measurements, or the derived error bounds. This makes the claim of "validating theoretical predictions" computationally untraceable from the artifacts.

## 2. The Four Questions
- **Problem**: Explaining the discrepancy between constant-depth expressivity limits and the empirical success of deep parallelizable models (Transformers/SSMs).
- **Novelty**: High. Transforming a qualitative "solvable" boundary into a quantitative $\mathcal{O}(\epsilon^{2^{k-1}+1})$ scaling law is a distinct contribution beyond the *Merrill et al.* lineage.
- **Claim vs. Evidence**: 
    - **Scaling Claim**: The central claim is a doubly-exponential reduction in simulation error with depth $k$.
    - **Evidence Gap**: The evidence provided is primarily qualitative. Table 1 and Figure 2 measure **Accuracy**, which collapses simulation error into a discrete label. Figure 5 measures **MSE** but lacks a quantitative fit or regression to confirm the predicted $2^{k-1}$ exponent.
- **Empirical Support**: Weak for the specific scaling law. It establishes that "depth helps" (generic), but not that it helps in the specific functional form predicted by the Lie-algebraic theory.

## 3. Hidden-Issue Checks (The "Smoking Guns")

### 3.1. The Unvalidated Scaling Exponent
Corollary 3.6 predicts a very specific functional form for error decay: $\mathcal{O}(\epsilon^{2^{k-1}+1})$. For $k=1, 2, 3, 4$, the exponents are $2, 3, 5, 9$.
In the 3D rotation experiments (Figure 5), there is no attempt to verify this exponent. If the theory were "validated," one would expect a log-log plot of MSE vs. Depth (or a similar transformation) showing the predicted doubling of the exponent. Without this, the experimental results are consistent with *any* polynomial or exponential depth-improvement model.

### 3.2. Admitted Learnability Collapse (Selective Reporting)
The Figure 3 caption admits: *"Deep models (> 4 layers) that failed to achieve a longer sequence length than shallower models are not shown"*. 
This is a critical forensic finding. If the theory predicts exponential error reduction, the fact that models at $k=8$ often fail to outperform $k=4$ (achieving length 36 vs 35 for Signed Mamba) indicates that the **Optimization Topology** is the dominant factor, rendering the **Expressivity Bound** practically irrelevant for deep models in these group classes.

### 3.3. Width-Depth Confounding
Corollary 3.10 identifies that simulating free Lie algebras requires state spaces that grow exponentially in sequence length. However, the experiments use fixed-width models ($d=128$). The observed "saturation" in Figure 3 likely stems from this **Width Bottleneck**, yet the paper attributes it to "learnability" without disentangling the two.

## Final Assessment
The paper provides a beautiful theoretical scaffolding that is unfortunately decoupled from its empirical validation. The central "doubly-exponential" scaling prediction remains an unmeasured quantity, and the selective reporting of "successful" deep models masks the reality that gradient-based training cannot yet climb the Lie tower the paper describes.
