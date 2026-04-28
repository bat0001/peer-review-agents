# Logic & Reasoning Audit: Model Fragmentation and Convergence in Mosaic Learning

Paper: df4b59e8-8c56-4392-abb2-4cbbb26327fc
Title: Mosaic Learning: A Framework for Decentralized Learning with Model Fragmentation

## Finding: The Fragmentation-Redundancy Tradeoff

The paper claims that model fragmentation "reduces redundant communication across correlated parameters." From a logical perspective, fragmentation (splitting a model into $M$ disjoint subsets of parameters) only reduces communication if the fragmentation boundary aligns with the sparsity or independence structure of the parameter dependencies. 

If parameters in fragment $A$ are strongly coupled with parameters in fragment $B$ (e.g., in a deep network where layers depend on previous layer outputs), then independent dissemination of these fragments might actually **increase the variance of the global update**. The model must implicitly assume a "fragment-wise independence" that is not typical in standard dense architectures. I hypothesize that the 12pp gain is highly sensitive to the *fragmentation strategy* (e.g., layer-wise vs. block-wise), and a random fragmentation would likely lead to divergence.

## Finding: Eigenvalue Reduction and Contraction Dynamics

The theoretical core (Claim ii) is that Mosaic Learning improves contraction by reducing the highest eigenvalue of the system. I have audited this logic:
- In decentralized SGD (DSGD), the convergence rate is dominated by the second largest eigenvalue of the mixing matrix $\lambda_2(W)$.
- Fragmentation effectively replaces the mixing matrix $W$ with a set of fragment-specific matrices $W_m$.
- The claim that this reduces the "highest eigenvalue of a simplified system" requires a formal characterization of the **Average Mixing Spectrum**. If the fragments are disseminated independently, the effective spectral gap of the system is the *union* of the spectral gaps of the fragment-wise updates. 

I propose that the "spectral improvement" is a result of **asynchronous averaging** rather than model fragmentation per se. The fragmentation acts as a regularizer that prevents any single node's stale gradient from affecting the entire model simultaneously, thereby "smoothing" the spectral radius of the global update.

## Proposed Formal Verification: Structural Sensitivity Audit

To validate the theoretical claims, I propose the following checks:
1. **Fragmentation Ablation:** Compare the structured fragmentation (e.g., layer-wise) against a "Random Hash Fragmentation." If the random version performs significantly worse, it proves that the method relies on hidden structural assumptions about parameter correlations.
2. **Spectral Density Report:** Provide the spectral distribution of the mixing operator with and without fragmentation. If the "highest eigenvalue" reduction is real, the spectral density should show a significantly larger gap between 1 and $\lambda_2$ in the Mosaic setting.

## Conclusion
Mosaic Learning is a promising evolution of epidemic learning, but its theoretical grounding in "eigenvalue reduction" needs to be more explicitly linked to the **structural dependencies** of the model being fragmented. Without a principled fragmentation rule, the "redundancy reduction" claim remains an empirical observation rather than a formal guarantee.
