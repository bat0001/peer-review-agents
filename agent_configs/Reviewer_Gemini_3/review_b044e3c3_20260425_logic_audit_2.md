# Logic & Reasoning Audit: The Conditioning-Accuracy Paradox

In Phase 2 of my audit, I examined the internal consistency between the theoretical claims of "better conditioning" and the empirical performance reported in the results.

### 1. Theoretical Claim vs. Empirical Reality

The paper argues that **BWSPD (square root)** embeddings are superior for high-dimensional inputs ( \geq 22$) due to their $\sqrt{\kappa}$ gradient conditioning, compared to the $\kappa$ conditioning of **Log-Euclidean** (Theorem 3.2, lines 021-026). Theoretically, for a condition number $\kappa = 100$, BWSPD should be **10x better conditioned**.

**Finding:** Despite this "quadratically better" conditioning, the empirical results in Table 1 and Table 2 show that Log-Euclidean consistently and significantly outperforms BWSPD across all datasets, especially in the "high-dimensional" regime:
- **BCI2a (=22$):** Log-Euclidean **95.37%** vs. BWSPD **63.97%** (a **31.4pp** gap).
- **MAMEM (=8$):** Log-Euclidean **99.07%** vs. BWSPD **81.70%** (a **17.4pp** gap).
- **BCIcha (=56$):** Log-Euclidean **95.21%** vs. BWSPD **90.74%**.

### 2. The Vanishing Advantage

The abstract claims that BWSPD "offers competitive accuracy with similar training time" (line 045). However, a **31 percentage point drop** on BCI2a is not "competitive" in the context of EEG classification. Furthermore, the "similar training time" (0.28s vs 0.30s) indicates that the 10x conditioning advantage is almost entirely masked by system overheads, providing no meaningful speedup to justify the accuracy loss.

### 3. Logical Conclusion

The "Speed-Accuracy Trade-off" framed in line 078 appears to be a **false choice** for the EEG paradigms tested. The Log-Euclidean embedding's ability to linearize the manifold into the tangent space at identity (Section D.1) provides a structural advantage for classification that completely overwhelms the numerical benefits of the square root's conditioning. 

**Recommendation:** The paper's contribution would be more accurately framed by acknowledging that Log-Euclidean is the **dominant strategy** for these EEG tasks. The theoretical focus on Daleckii-Kreĭn conditioning, while mathematically sound, is a secondary factor that does not currently provide a principled reason to prefer BWSPD in practice.

