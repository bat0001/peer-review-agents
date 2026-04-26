# Reasoning and Evidence: Logical Audit of "Benchmarks Are Not That Out of Distribution"

## 1. Finding: Logical Leap in the Critique of n-gram Cross-Entropy

In Section 3.2 and Appendix A, the authors argue that $n$-gram cross-entropy ($n \ge 2$) is an "unreliable proxy" for measuring dataset overlap because it is "dominated" by Markov misspecification.

### Mathematical Context
The paper provides a decomposition of the $n$-gram cross-entropy (Equation 13, Appendix A):
$$H(P_B, Q_A^{(n)}) = H(P_B) + D_{\mathrm{KL}}(P_B \| P_B^{(n)}) + D_{\mathrm{KL}}(P_B^{(n)} \| P_A^{(n)})$$

- $H(P_B)$: Entropy rate of the source.
- $D_{\mathrm{KL}}(P_B \| P_B^{(n)})$: Markov misspecification (information lost by truncating context to $n-1$).
- $D_{\mathrm{KL}}(P_B^{(n)} \| P_A^{(n)})$: Dataset mismatch within the Markov family.

### The Logical Gap
The authors claim that the Markov misspecification term "dominates the cross-entropy for realistic $n$, masking differences due to genuine distributional mismatch" (Section 3.2). 

However, this is an **empirical claim** about the relative magnitudes of the terms, which the paper **does not test**. The paper does not provide:
1. An empirical comparison of $n$-gram cross-entropy vs. unigram cross-entropy as predictors of benchmark performance.
2. An assessment of whether the $D_{\mathrm{KL}}(P_B^{(n)} \| P_A^{(n)})$ term (the actual "mismatch") is indeed "masked" (i.e., its variance across datasets is small relative to the misspecification term).

The conclusion that $n$-gram models are "unreliable" for this specific purpose is a logical leap from a theoretical decomposition to an untested empirical conclusion. It is possible that $n$-gram cross-entropy, despite the misspecification bias, remains a stronger predictor of performance because it captures local syntactic alignment which unigrams ignore.

## 2. Finding: Contradictory Results for the BLiMP Benchmark

There is a direct contradiction between the main text's characterization of the BLiMP benchmark and the results presented in the Appendix.

### Evidence
**Table 6 (Main Text, Page 7):** Reports results for a 1.33B model on 26B tokens.
- **DCLM**: Entropy 12.42, Score **61.01**
- **C4**: Entropy 12.66, Score **80.48**
- **FineWeb-Edu**: Entropy 12.87, Score **80.89**
*Observation*: Lower entropy (DCLM) corresponds to a significantly *lower* score, supporting the authors' claim that grammatical benchmarks do not follow the word-overlap trend.

**Table 13 (Appendix, Page 15):** Reports results for a 3.36B model on 60B tokens.
- **DCLM**: Entropy 12.42, Score **85.03**
- **C4**: Entropy 12.66, Score **81.01**
- **FineWeb-Edu**: Entropy 12.87, Score **80.00**
*Observation*: Lower entropy (DCLM) now corresponds to a *higher* score. The Appendix explicitly states: "**Contrary to table 6**, BLiMP exhibits an inverse relationship between word-level unigram cross-entropy and benchmark performance."

### Logical Implication
The authors use Table 6 to argue that BLiMP is an exception that requires "grammatical knowledge grounded in higher-order, contextual representations" (Section 5.1). However, Table 13 shows that at a larger scale, the "word-overlap trend" actually returns. This suggests that the "grammar" exception is not an intrinsic property of the benchmark type as claimed, but rather a transient artifact of smaller model/data scales. The paper fails to reconcile this contradiction or address why the mechanism changes with scale.

## 3. Recommendation
The authors should:
1. Empirically validate the claim that $n$-gram cross-entropy is a worse predictor than unigram cross-entropy.
2. Reconcile the conflicting BLiMP results across scales to clarify whether grammatical knowledge is indeed independent of unigram alignment.
