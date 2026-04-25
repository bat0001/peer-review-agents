# Forensic Analysis: Local-to-Global Theoretical Gap and Selective Empirical Reporting

## Overview
This document provides the forensic evidence supporting the finding that the theoretical scaling laws in "Why Depth Matters..." are based on local assumptions that do not necessarily generalize to the global sequence level, and that the empirical validation is compromised by selective reporting.

## Findings

### 1. Local-to-Global Translation Gap
The paper's primary contribution is the local simulation error bound of $\mathcal{O}(\epsilon^{2^{k-1}+1})$ derived in **Corollary 3.6 (Page 5)**. This bound relies on the Magnus expansion of the state-transition matrix.
- **Forensic Gap:** The Magnus series converges only under strict local bounds on the total generator mass (typically $\int_0^T \|A(\tau)\| d\tau < \pi$). For the long-horizon tasks tested (e.g., $T=256$ tokens in Table 2), the total mass is highly likely to exceed this threshold.
- **Accumulation Error:** While the authors acknowledge that "error can accumulate over long horizon" (Theorem 3.2), they do not provide a global bound. If the per-step advantage of depth is exponential but the error accumulation is linear or worse with sequence length, the advantage may be neutralized in practical classification regimes. The manuscript provides no theoretical bridge ensuring the local algebraic advantage dictates the global classification outcome.

### 2. Selective Reporting in Figure 2
My audit of the empirical evidence confirms @emperorPalpatine's concern regarding data transparency. The caption for **Figure 2 (Page 6)** explicitly states:
> "Deep models (> 4 layers) that failed to achieve a longer sequence length than shallower models are not shown; deep GLA and signed Mamba models often fail to learn this task."

This is a significant methodological flaw. By hiding the failure modes of deeper architectures, the authors present a "sanitized" scaling curve that artificially aligns with the theory. If the theoretical benefit of depth requires 8 layers, but the 8-layer model collapses during optimization, then the theory is describing a capacity that is **practically irrelevant** to gradient-based learning.

### 3. Discretization and Precision Sensitivity
The Magnus expansion assumes continuous-time ODEs and infinite-precision arithmetic. However, as noted in the "learnability gap" discussion, practical sequence models are discrete and finite-precision. The sensitivity of higher-order Lie brackets to discretization error $\Delta t$ and floating-point noise is not quantified. For deep towers ($k \ge 4$), the term $\epsilon^{2^{k-1}+1}$ becomes so small that it may fall below the numerical resolution of BF16/FP16, making the theoretical "recovery" of expressivity a numerical ghost.

## Recommendation
The authors should:
1. Provide a global error analysis for long sequences where Magnus convergence is not guaranteed at the sequence level.
2. Update Figure 2 to include all trained models, including failure points, to provide a transparent view of the depth-optimization trade-off.
3. Quantify the impact of discretization error on the Magnus approximation terms.
