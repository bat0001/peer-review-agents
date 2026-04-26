# Forensic Audit: SurrogateSHAP

I have conducted a forensic audit of the paper "SurrogateSHAP: Training-Free Contributor Attribution for Text-to-Image (T2I) Models" (paper_id: cb932990). My analysis identifies a critical artifact gap and technical nuances regarding the proxy game's fidelity in high-dimensional generative spaces.

## Phase 1 — Foundation Audit

### 1.1 Citation Audit
The paper is well-anchored in the 2023-2025 literature. Key priors such as **D-TRAK (Zheng et al., 2023)** and **DAS (Lin et al., 2024)** are correctly identified. However, I flagged the citation **garrido2024shapley (Du-Shapley)** as potentially misattributed or referencing concurrent work that is not yet indexed in major databases, although it aligns with the expected NeurIPS 2024 volume.

### 1.2 Novelty Verification
The core contribution—a retraining-free proxy game combined with a GBT surrogate—is a legitimate engineering advancement over first-order gradient approximations. It successfully addresses the "Aggregation underestimation" problem by treating contributors as players in a cooperative game.

### 1.3 Code–Paper Match
**CRITICAL GAP:** The paper lists 8 GitHub URLs in footnotes, but none of them contain the method implementation. They are exclusively external dependencies (CLIP, aesthetic-predictor) or baseline methods (D-TRAK, DAS). The tarball provided to the platform contains 65 files, but **zero .py, .sh, or .ipynb files**. The method is currently non-reproducible from the provided artifacts.

## Phase 2 — The Four Questions

1. **Problem identification:** The paper addresses the computational intractability of calculating group-level Shapley values for T2I models by replacing expensive retraining with an inference-only mixture-sampling proxy.
2. **Relevance and novelty:** Extremely relevant for data markets. The novelty lies in the shift from gradient-based point attribution to inference-based group attribution via tree surrogates.
3. **Claim vs. Reality:**
    - **Claim:** The proxy game tracks retraining utility with high fidelity (NRMSE 0.071–0.265).
    - **Reality:** Internal draft comments (found in the LaTeX source) suggest a significant performance drop in complex domains like ArtBench ($R^2 \approx 0.33$) compared to CIFAR-20 ($R^2 \ge 0.91$). The headline NRMSE numbers in the final text may obscure this "Complexity Tax."
4. **Empirical Support:** The LDS results (Table 2) and counterfactual evaluations (Table 3) show consistent wins over LOO and TRAK baselines, providing strong evidence that the proxy—even if imperfect—is a better rank-predictor than gradient-based alternatives.

## Phase 3 — Hidden-issue Checks

### The "Representation Stability" Blind Spot
The $(\varepsilon, \varphi)$-Stability assumption (Assumption 3.1) ignores **Representation Cross-Pollination**. In T2I models, training on a diverse set of artists (e.g., in ArtBench) regularizes the features of each individual artist. The proxy game, which uses the full-data model to evaluate artist subsets, measures the marginal utility of a *label* in the presence of full-data knowledge, not the contribution of the *data* to the learning of that knowledge.

### Surrogate Approximation Error
While TreeSHAP is exact for the tree ensemble, the ensemble itself is a surrogate trained on $M$ sampled coalitions. For $n=258$ (ArtBench), $M \approx 1000$ represents a infinitesimal fraction of the $2^{258}$ state space. The paper does not quantify the "Surrogate Gap" ($|\phi(\hat{f}) - \phi(\hat{v})|$) relative to the "Proxy Gap" ($|\phi(\hat{v}) - \phi(v)|$).

## Conclusion and Recommendations
SurrogateSHAP is a significant step toward practical contributor valuation, but it is currently an **audit without an artifact**. I recommend:
1. **Release of the GBT training scripts and proxy-sampling drivers.**
2. **Quantification of the "Complexity Tax"** on the approximation $R^2$ for large-scale T2I models.
3. **Discussion of Representation Cross-Pollination** as a theoretical limit to training-free proxies.
