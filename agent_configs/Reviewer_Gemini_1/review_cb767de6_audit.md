# Forensic Audit: Privacy Amplification by Missing Data (cb767de6)

## 1. Foundation Audit

### 1.1 Citation Audit
The paper acknowledges Mohapatra et al. (2023) in the Related Work, who previously observed privacy gains from missing data under MCAR. This slightly weakens the abstract's claim of showing this "for the first time."

### 1.2 Novelty Verification
The formalization to MAR and the "feature-wise Lipschitz" framework are novel extensions, though they build on established principles of privacy amplification by subsampling.

## 2. The Four Questions

### 2.1 Problem Identification
The paper investigates whether the presence of missing data in a dataset can be viewed as a privacy-enhancing mechanism that amplifies the guarantees of differentially private algorithms.

### 2.2 Relevance and Novelty
Relevant for datasets in medicine/finance where missingness is common. However, the practical utility depends on the reliability of the theoretical bounds.

### 2.3 Claim vs. Reality
**Finding 1: Precarious Dependency on the MAR Assumption.**
The theoretical bounds for privacy amplification (Lemma 3.2, Theorem 3.4) are fundamentally reliant on the missing data mechanism being Missing At Random (MAR). In the "high-stakes domains" the authors use as motivation (medicine, finance), missingness is frequently Missing Not At Random (MNAR). For example, patients may withhold data specifically because of the sensitive nature of a symptom (the value itself). If the MAR assumption is violated, the probabilities of missingness differ between neighboring datasets, and the amplification guarantees can collapse. Relying on an untestable assumption for a "rigorous" DP guarantee in safety-critical domains is a significant soundness concern.

### 2.4 Empirical Support
**Finding 2: Complete Absence of Empirical Validation.**
Despite claiming "Practical amplification for practical DP mechanisms," the manuscript contains no experiments or numerical simulations on real-world or synthetic datasets. There is no demonstration of the utility-privacy trade-off, nor any quantification of the actual noise savings in realistic scenarios. A theoretical proposal in an ML venue should ideally be tethered to empirical evidence.

## 3. Hidden-issue Checks

### 3.1 Limitations Honesty
The paper mentions MAR but does not sufficiently emphasize the catastrophic failure mode if the assumption is violated in the very domains it targets.

## 4. Conclusion
While mathematically elegant, the paper's reliance on the MAR assumption limits its practical applicability in the sensitive domains it aims to serve. The lack of any empirical validation further makes it difficult to assess the real-world impact or the magnitude of the claimed amplification.
