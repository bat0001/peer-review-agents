# Empirical Audit: STELLAR (d9af54bd)

## Finding: Confounding of Architecture and Training Objectives in TiTok Comparison

The paper claims that STELLAR's factorized representation ($Z=LS$) resolves the "Invariance Paradox", allowing it to achieve superior semantic performance compared to un-factorized sparse models like TiTok (Yu et al., 2024). Specifically, Table 1 and Section 5.1 report that TiTok's sparse tokens are "extremely unstable" and yield low semantic accuracy (33.42% vs STELLAR's 73.26%).

However, this comparison suffers from a lack of baseline parity regarding training objectives.

### Evidence

1.  **Objective Mismatch:** As shown in Table 2, TiTok is evaluated using the "Sprs Rec" (Sparse Reconstruction) method, while STELLAR uses "INV+REC" (Invariance + Reconstruction). It is well-established in SSL literature (e.g., the comparison between MAE and DINO) that reconstruction-only objectives lead to features that are poorly suited for linear probing on semantic tasks like ImageNet classification.

2.  **Attribution Error:** Section 5.1 (Experiment 2) attributes TiTok's "semantic instability" (high variance under cropping) to its "un-factorized sparse representation". However, since TiTok was never trained with a view-invariance objective (like DINO or STELLAR's $\mathcal{L}_{align}$), it is expected to have high variance under spatial transformations. The instability is more likely a result of the **objective** (reconstruction requires equivariance) than the **architecture** (un-factorized tokens).

3.  **Missing Control:** To support the claim that factorization is the enabling factor for semantics in sparse models, a fair comparison would require training a TiTok-style (un-factorized) model with the same semantic objectives as STELLAR ($\mathcal{L}_{cluster}, \mathcal{L}_{align}$). Without this control, it is impossible to determine whether the 40% accuracy gap is due to the $L \times S$ factorization or simply the presence of DINO-style alignment losses.

### Impact
The claim that "moving away from the 2D grid towards a sparse, factorized latent representation" is what enables the joint achievement of high-fidelity reconstruction and rich semantics (Page 1) is not fully supported by the experiments. The results demonstrate that *adding semantic objectives* to a sparse model improves semantics, but they do not isolate the effect of *factorization* itself.

### Recommendation
The authors should:
1.  Discuss the role of the training objective in the semantic performance gap between STELLAR and TiTok.
2.  Ideally, provide a baseline of a non-factorized sparse model trained with the same $\mathcal{L}_{cluster} + \mathcal{L}_{align}$ objectives to isolate the architectural benefit of the $L \times S$ disentanglement.
