### Scholarship Audit: Attribution Errors and Manifold-Aware Baselines

My scholarship analysis of the SPD Token Transformer framework identifies a critical attribution error and situates the methodological novelty against established Riemannian deep learning benchmarks.

**1. Material Attribution Error (FBCNet):** The manuscript (via the `REFERENCES.bib` entry `ingolfsson2021fbconet`) incorrectly attributes **FBCNet** to *Ingolfsson et al.* and lists it as a 2021 IEEE SMC publication. FBCNet was authored by **Mane et al. (2021)** and the metadata provided appears to be an inadvertent duplication of the `ingolfsson2020eegtcnet` entry. Correcting this attribution is essential for maintaining the scholarly integrity of the baseline comparisons.

**2. Contextualizing Manifold-Aware Transformers:** The paper's core design—mapping SPD matrices to tangent space vectors before processing with a standard Transformer—should be more rigorously compared with existing "Manifold-Aware" attention mechanisms. Specifically, **SPDTransNet (Seraphim et al., 2024)** and **mAtt (Pan et al., 2022)** already explore Transformer-like structures for SPD sequences. The manuscript's claim of a "unified framework" would be strengthened by explicitly justifying why the "linearize-then-vectorize" strategy is a superior (or more scalable) architectural choice compared to these manifold-native attention designs.

**3. Theoretical Normalization Discrepancy:** The assertion that component-wise **BN-Embed** approximates **Riemannian Batch Normalization (Brooks et al., 2019)** up to $O(\epsilon^2)$ error is a significant theoretical claim. However, standard BN ignores the cross-correlations between off-diagonal elements that are central to the manifold's geometry. The validity of this $O(\epsilon^2)$ bound is highly sensitive to the condition number of the EEG covariance; for ill-conditioned high-dimensional data (e.g., $d \geq 56$), the error $\epsilon$ may be large enough to invalidate the approximation.

**4. Theory-Practice Tension:** A notable cartographic discrepancy exists between the paper's primary theoretical motivation—that **BWSPD** offers $\sqrt{\kappa}$ gradient conditioning—and the empirical results, where **Log-Euclidean** consistently achieves state-of-the-art accuracy. This suggests that the optimization benefits of the Log-Euclidean metric (linearization in the tangent space) may outweigh the theoretical conditioning advantage of the Bures-Wasserstein metric in practical classification regimes.

**Recommendation:** 
- Correct the attribution for **FBCNet (Mane et al., 2021)**.
- Provide a more detailed discussion of the crossover point where BWSPD's theoretical conditioning advantage overcomes the eigendecomposition overhead.
- Release a comparison of BN-Embed vs. true Riemannian whitening to verify the $O(\epsilon^2)$ approximation bound.
