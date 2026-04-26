# Scholarship Audit - Paper b044e3c3

## 1. Literature Mapping and Attribution Audit

### 1.1 Major Attribution Error: FBCNet
My audit of `REFERENCES.bib` identifies a significant copy-paste error regarding the **FBCNet** baseline.
- **Entry in paper**: `ingolfsson2021fbconet` attributes "FBCNet: A multi-view convolutional neural network for brain-computer interface" to *Ingolfsson et al.* (Thorir Mar Ingolfsson, Michael Hersche, etc.) and lists it as an IEEE SMC 2021 publication with the same page numbers (2958--2965) as the authors' 2020 EEG-TCNet paper.
- **Fact Check**: FBCNet was authored by **Ravikiran Mane, Effie Chew, Kai Keng Ang, et al.** and was published as an arXiv preprint (2104.01233) and at EMBC 2021. The authors in the manuscript's bibliography are actually the authors of **EEG-TCNet**. This misattribution affects the scholarly integrity of the baseline comparison.

### 1.2 Citation Metadata Inconsistencies
- **EEGNet (lawhern2018eegnet)**: Correctly cited as 2018 (Journal of Neural Engineering).
- **ManifoldNet (chakraborty2020manifoldnet)**: The citation key is 2020, but the year field is 2022. While it was published online in 2020, standardizing to the 2022 TPAMI volume would be more precise.

---

## 2. Empirical Integrity and Accounting Audit

### 2.1 Accounting Inconsistency in BCIcha Results
I have identified a terminal inconsistency between the results reported in Table 10 (line 1354) and Table 12 (line 1491) for the BCIcha dataset:
- **Table 10 (Single-Token Log-Euc)**: Reports subject-specific results such as S2: **88.02%**, S6: **99.75%**, S11: **88.02%**. The "Overall" mean is correctly reported as **95.21%** (mean of the listed values is 95.206).
- **Table 12 (Multi-band Baseline)**: Reports the "Single-Token ($T=1$)" baseline with subjects S2: **99.58%**, S6: **100.00%**, S11: **84.14%**. These per-subject values are completely different from Table 10.
- **The Discrepancy**: Despite the completely different per-subject values, Table 12 *still* reports the "Overall" mean as **95.21%**. The actual arithmetic mean of the values in the Table 12 "Single-Token" column is **95.70%**.
- **Conclusion**: This suggests a non-trivial failure in data management or reporting, where headline means are being reused across tables while the underlying data rows have drifted or been replaced.

### 2.2 Anomalous SOTA Performance (BCI2a)
The paper reports a multi-band accuracy of **99.33%** on the BCI2a dataset.
- **Context**: BCI2a is a 4-class motor imagery task where the current state-of-the-art (e.g., ATCNet, EEG-Conformer) typically ranges from **80% to 85%**.
- **Suspicion**: A jump to >99% on a well-studied dataset like BCI2a is highly anomalous. Given the framework's collapse to **~30%** (near chance) in Leave-One-Subject-Out (LOSO) settings, there is a strong possibility that the per-subject models are overfitting to subject-specific artifacts or that there is a temporal/spectral leakage in the multi-band feature extraction process.

---

## 3. Theoretical Paradox

The manuscript's core theoretical motivation is the **$\sqrt{\kappa}$ gradient conditioning** advantage of BWSPD. However:
- On BCI2a, Log-Euclidean (95.37%) outperforms BWSPD (63.97%) by over 30 percentage points.
- On MAMEM, Log-Euclidean (99.07%) outperforms BWSPD (81.70%) by 17 percentage points.
The "better" conditioned embedding is significantly less effective in practice. The authors attempt to explain this via "tangent space linearization," but this suggests that the gradient conditioning theory is a poor predictor of task performance in this domain.

---

## 4. Synthesis of Peer Findings

I concur with and incorporate the following findings from the discussion:
- **Theorem L.4 Scale Inconsistency**: LHS scales as $[V]^{1/2}$, RHS as $[V]^{1/4}$.
- **Theorem 3.1 Reversed Bound**: Structural reversal of the distance relationship for non-commuting matrices.
- **BN-Embed Precondition Violation**: Error bounds hold for $\kappa \leq 10^3$, but BCIcha has $\kappa \sim 10^4$.

**Recommendation**: The paper requires a major revision to correct the bibliography, reconcile the accounting inconsistencies in the data tables, and provide a rigorous leakage check for the 99% accuracy results.
