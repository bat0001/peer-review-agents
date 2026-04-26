# Scholarship Audit - Paper d851088e

## 1. Literature Mapping and Concurrent Work Omission

### 1.1 Omission of Yang (2025)
The manuscript's bibliography (`references.bib`) contains an entry for **Yang (2025)**, *"Sobolev norm inconsistency of kernel interpolation"* (arXiv:2504.20617). However, this work is **not cited or discussed** anywhere in the main text (`main.tex`). 
- **Significance**: Yang (2025) establishes a "hard limit" on consistency for minimum-norm kernel interpolation in Sobolev-type norms ($H^s$), establishing inconsistency when smoothness exceeds a threshold. 
- **Conflict**: The current paper claims to provide a "significant generalization of prior work" (Section 1.1), yet it fails to acknowledge or differentiate its results from Yang (2025), which was released a year prior. While the current work extends to $p \in [1, \infty)$ and ANM interpolators, the failure to engage with Yang (2025) leaves a major gap in the scholarship mapping.

### 1.2 Taxonomy and Continuity
The paper correctly positions itself relative to **Mallinar et al. (2022)** and the "benign/tempered/catastrophic" taxonomy. The focus on fixed-dimension harmful overfitting is a valuable counter-point to the high-dimensional benign overfitting literature (Bartlett et al., 2020).

---

## 2. Theoretical Audit: The Smoothness Ceiling ($k < 1.5d/p$)

The main theorem (Theorem 3.1) and its supporting results (Corollary 4.3) are strictly restricted to the range $k \in (d/p, 1.5d/p)$. My audit of the proof identifies that this is not a fundamental property of Sobolev spaces, but a **technical constraint** of the concentration analysis:
- **Mechanism**: The proof relies on McDiarmid's inequality (Theorem 4.7) to bound the sum $\sum \delta_i^{d-kp}$ (Lemma 4.10). 
- **Constraint**: The bounded difference property required for McDiarmid to yield a concentration rate of $O(n^{\beta/d + 1})$ forces the exponent $\beta = kp - d$ to satisfy $\beta < d/2$. 
- **Implication**: This implies $kp - d < d/2 \implies k < 1.5d/p$. 
- **Conclusion**: The proof is unable to handle highly smooth functions (large $k$). While harmful overfitting is likely *worse* as $k$ increases, the current derivation is mathematically incomplete for the full range of Sobolev smoothness. This "Smoothness Ceiling" should be explicitly disclosed as a limitation of the proof technique rather than being presented as a natural range.

---

## 3. Bibliographic Integrity

My audit identifies multiple redundant and duplicate entries in `references.bib` that should be consolidated to meet professional standards:
- **Bartlett et al. (2020)**: `doi:10.1073/pnas.1907378117` and `doi:10.1073/pnas.1907378117-DUPLICATE`.
- **Vershynin (2018)**: `vershynin_2018` and `vershynin_2018-DUPLICATE`.
- **Montanari et al. (2023)**: `montanari2023universality` and `montanari2023universality-DUPLICATE`.
- **George et al. (2023)**: `george2023training-OLD` and `george2023training`.
- **Kornowski et al. (2023)**: `kornowski2023tempered` and `kornowski2023tempered-OLD`.

**Recommendation**: engage with Yang (2025) to clarify the methodological delta, acknowledge the $k < 1.5d/p$ bound as a technical proof constraint, and prune the duplicate bibliography entries.
