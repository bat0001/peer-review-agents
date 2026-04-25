# Forensic Analysis: Benchmarks Are Not That Out of Distribution

**Paper ID:** a4001e85-7e0e-4ee3-98d7-f234c7aeaae5
**Title:** Benchmarks Are Not That Out of Distribution: Word Overlap Predicts Performance
**Authors:** Woojin Chung, Jeonghoon Kim (2026)

## Phase 1: Foundation Audit

### 1.1 Citation Audit
- **Seminal Works:** Cites Hendrycks (MMLU), Penedo (FineWeb), Li (DCLM), and Dodge (C4/Contamination) correctly.
- **Novelty vs. Prior Work:** Cites Chung & Kim (2025) "Exploiting vocabulary frequency imbalance in language model pre-training". The authors argue the current work is an extension to external evaluation.
- **SOTA Cartography:** The paper maps the latest SOTA corpora (FineWeb-Edu, DCLM) and models.

### 1.2 Novelty Verification
- The core contribution is identifying **word-level unigram cross-entropy** as a predictor of benchmark performance across model scales and datasets.
- While "Data Contamination" is a known concept (Dodge et al., 2021), this paper formalizes it as "Statistical Overlap" and provides a quantitative proxy that doesn't require exact substring matching.

### 1.3 Code-Paper Match
- No repository link provided. This is a minor reproducibility concern given the experimental scale.

## Phase 2: The Four Questions

### 1. Problem Identification
- Benchmarks are assumed to measure abstract generalization (OOD), but they may primarily reflect marginal distributional similarity (statistical overlap) with the pre-training corpus.

### 2. Relevance and Novelty
- Highly relevant given the reliance on "zero-shot" benchmarks for model ranking. Novel in its use of a tokenizer-agnostic, information-theoretic metric (unigram cross-entropy) to quantify this overlap.

### 3. Claim vs. Reality
- **Claim:** Unigram cross-entropy predicts performance.
- **Evidence:** Figure 1 and Table 7 show a near-perfect mirroring of entropy and accuracy rankings across ARC, Hellaswag, MMLU, etc.
- **Claim:** Trend holds at scale.
- **Evidence:** Table 15 shows that even "reasoning" tasks (BLiMP, MathQA) follow the trend at 3.36B scale, despite initially appearing as exceptions at smaller scales (Table 4).

### 4. Empirical Support
- **Ablations:** The "bigger word count" experiment (Table 2) isolates frequency from entropy.
- **Statistical Rigor:** Table 3 reports mean and std across 5 independent subsets, confirming the trend is not an artifact of subset sampling.

## Phase 3: Hidden-Issue Checks

### 3.1 The Scale-Dependent Reversal (The "Reasoning" Illusion)
A critical forensic finding is the transition between Table 4 and Table 15. The authors initially state that BLiMP and MathQA "cannot be explained by unigram cross-entropy alone" based on 1.33B models. However, at 3.36B models, the relationship **reappears**.
- **Finding:** "Reasoning" tasks only appear to be OOD or "true reasoning" when the model is capacity-limited. As models grow, they increasingly "compress" the marginal distribution of even complex benchmarks, making their success predictable by unigram statistics.
- **Anchor:** Page 7 (Table 4) vs. Page 25 (Table 15).

### 3.2 Laplace Smoothing and Vocabulary Bias
The unigram cross-entropy metric (Eq 3.1) uses Laplace smoothing ($+1$) for out-of-vocabulary (OOV) words.
- **Issue:** Different pre-training corpora have different vocabulary sizes $|V|$ and total token counts $N$. The probability assigned to an OOV word is roughly $1/(N + |V|)$.
- **Forensic Concern:** If one corpus is significantly larger or has a more diverse vocabulary, its penalty for missing benchmark words might be systematically higher or lower, potentially biasing the cross-entropy ranking. The paper does not report $|V|$ or control for vocabulary size parity.

### 3.3 The Multilingual Boundary
Figure 3 (Page 7) shows the trend **fails** for multilingual zero-shot tasks (Global PIQA, LAMBADA multilingual).
- **Finding:** The "Statistical Overlap" hypothesis is restricted to the language of pre-training. This suggests that "Generalization" in multilingual settings is qualitatively different from the "Pattern Matching" observed in monolingual benchmarks. This boundary is under-emphasized in the conclusion.

## Phase 4: Recommendation

**Finding 1: The Reappearing Trend.** Highlight that "reasoning" tasks follow the unigram trend at scale, suggesting they are not "true" OOD challenges for large models.
**Finding 2: Metric Sensitivity.** Request clarification on whether vocabulary size differences across FineWeb, DCLM, and C4 affected the Laplace-smoothed unigram cross-entropy.
**Finding 3: Multilingual Generalization.** Note that the failure of the trend in Figure 3 contradicts the "Generalization as Compression" framing if applied universally.
