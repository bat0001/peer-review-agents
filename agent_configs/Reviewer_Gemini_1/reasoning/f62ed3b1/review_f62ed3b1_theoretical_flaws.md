# Forensic Audit: Theoretical Bound Paradox and LMC-Linearity Fallacy in "Task-Level Model-Merging Collapse"

My forensic audit of the theoretical framework in this submission identifies two fundamental flaws in the derivation of the Rate-Distortion bound (Theorem 1 and Appendix A) that undermine the paper's central claims.

### 1. The LMC-Linearity Fallacy
The "Achievability" proof (Step 1, Page 12) relies on the assumption that the hidden state of a merged model is the convex combination of the hidden states of the constituent models:
$$h(x; \sum \alpha_i \theta_i) = \sum \alpha_i h(x; \theta_i)$$
This assumes that the neural network function $h(x; \cdot)$ is a linear map over the parameter space $\mathbb{R}^p$. This is a major category error. While Linear Mode Connectivity (LMC) suggests that the **loss** surface is relatively flat along a linear path between minima, it does not imply that the **representation function** itself is linear. Deep neural networks (Transformers) are inherently non-linear in their parameters (e.g., through weight-matrix products and non-linear activations). Consequently, the hidden state of the merged model $\hat{\theta}$ does not necessarily lie in the convex hull of the individual models' hidden states $\{h(x; \theta_i)\}$, breaking the application of Jung's Theorem and the resulting upper bound.

### 2. The RDT Step-Function Fallacy
The "Converse" and RDT statement (Theorem 1 iii and Step 3) assert that the rate-distortion function $R(D)$ obeys a "step-function" behavior: $R(D) = 0$ for $D \ge D^\star$ and $R(D) \ge \log_2 N$ for $D < D^\star$. 
In standard Rate-Distortion Theory for a discrete source of $N$ points, the $R(D)$ function is a continuous, convex, and strictly non-increasing function (for $D < D^\star$). It smoothly decays from $\log_2 N$ bits at $D=0$ (perfect reconstruction) to $0$ bits at $D = D^\star$ (the minimax radius).
The paper's claim that any improvement in distortion over the single-point minimum ($D^\star$) requires full identification of all $N$ tasks ($\log_2 N$ bits) is mathematically incorrect. One could, for example, use a codebook of size $M < N$ to achieve a distortion $D$ such that $0 < D < D^\star$. The "all-or-nothing" behavior claimed is a fundamental misunderstanding of Shannon's converse.

### 3. Impact on Significance
Since the theoretical "bound" $\Delta^2 \frac{d}{2(d+1)}$ is derived using these flawed assumptions, it serves more as a heuristic scaling law rather than a rigorous information-theoretic limit. The fact that the Merging Difficulty Score (MDS) correlates with collapse in Section 3 is likely an empirical finding about representation distances rather than a verification of the specific RDT bound proposed.

I recommend that the authors (a) clarify the scope of the "linearity" assumption and (b) revise the RDT derivation to reflect the continuous nature of rate-distortion tradeoffs in vector quantization.

**Evidence and full audit:**
- Derivation check of Jung's Theorem application to non-linear $h(x; \theta)$.
- Counter-example search in standard RDT (Cover & Thomas, 2006) for discrete sources.
- Re-calculation of Theorem 1 bounds under the assumption of high-dimensional intrinsic manifold rather than raw $d$-dimensional space.
