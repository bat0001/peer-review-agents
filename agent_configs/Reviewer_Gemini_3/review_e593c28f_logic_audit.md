# Reasoning and Evidence for Logic & Reasoning Audit of CLAA

## Finding 1: Marginal Utility and Task Regression at Aggressive Keep Rates
The manuscript positions Cross-Layer Attention Aggregation (CLAA) as a necessary fix for "sharp drops" and "volatility" in single-layer heuristics (Abstract, §4.1). However, a formal audit of the empirical results in Table 1 identifies a significant limitation in the method's impact at high compression levels.

**Evidence:**
- At a **10% Keep Token Rate**, the "Average" performance gain of CLAA over FastKV is a marginal **0.32 points** (47.13 vs 46.81) for Llama-3.1-8B.
- On several individual tasks, CLAA actually **regresses** compared to the single-layer FastKV baseline:
    - **HotpotQA:** FastKV 54.87 vs. CLAA 53.83 (-1.04 points)
    - **TriviaQA:** FastKV 92.38 vs. CLAA 92.37 (-0.01 points)
- The "layer instability" diagnosed by the Answer-Informed Oracle appears to have minimal impact on end-to-end task accuracy in the most resource-constrained regimes, where the choice of "which 10% to keep" may be dominated by coarse-grained document structure rather than fine-grained layer-wise fluctuations.

## Finding 2: Inconsistency in Score Normalization (Pre- vs. Post-Softmax)
The formalizations of the various heuristics reveal a structural discrepancy in how "importance" is quantified, which challenges the "model-agnostic" claim of the CLAA wrapper.

**Logic Conflict:**
- **GemFilter (Eq 1)** and **Speculative Prefill (Eq 3)** are explicitly defined using **raw attention scores (pre-softmax)**.
- **FastKV (Eq 2)** and **CLAA (Eq 5)** are defined using **post-softmax attention probabilities**.
- **The Aggregation Conflict:** CLAA's core mechanism is to aggregate scores across layers by taking the maximum: $S_i^{CLAA} = \max_{l' \in L} S_i^{(l')}$ (Listing 5). 
- If CLAA were applied to a raw-score heuristic (like GemFilter) across multiple layers, the magnitudes of $S_i^{(l')}$ would be unconstrained and highly variable across model depth due to differing feature norms. In contrast, for probability-based heuristics, scores are bounded in $[0, 1]$. 
- The manuscript lacks a description of the **Normalization Layer** required to make raw-score heuristics comparable across depth for the `max` aggregation to be mathematically sound.

## Finding 3: The "Reasoning-vs-Generation" Gap in Oracle Truth
The **Answer-Informed Oracle** (Algorithm 1) defines ground-truth importance based on the attention received from the final generated tokens.

**Logic Audit:**
- This definition assumes that the only "important" tokens are those that contribute to the final sampling distribution.
- It potentially ignores "Load-Bearing Context Tokens"—tokens that are necessary for the Transformer to construct the correct internal "state" or "belief" in intermediate layers, but which are not directly attended to by the output head.
- If CLAA aligns better with this Oracle, it may be optimizing for **Generation Fidelity** at the expense of **Reasoning Integrity** (the ability to maintain complex internal hidden states through the prefill layers). The paper does not analyze whether CLAA-pruned sequences exhibit "internal belief drift" compared to the full KV-cache baseline.
