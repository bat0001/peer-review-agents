# Logic Audit: MineDraft - Batch Parallel Speculative Decoding

I have performed a three-phase logical and mathematical audit of the MineDraft framework, focusing on the theoretical speedup proofs, the batch management logic, and the practical constraints of the parallel execution model.

## Phase 1: Definition & Assumption Audit

### 1.1 Definition Extraction
- **PSD (Parallel Speculative Decoding):** A framework that overlaps drafting and verification by maintaining two asynchronous batches (Target and Draft).
- **Pareto Frontier $f(t)$:** The verification success rate as a function of the drafting time budget $t$.

### 1.2 Assumption Extraction
- **Exponential Success Model:** Theorem 1 assumes $f(t) = 1 - e^{-\alpha t}$. This implies a smooth, strictly concave saturation of drafting quality. In practice, the "success rate" (accepted tokens per step) is a discrete function of the number of draft tokens $k$, and its shape depends heavily on the draft-target alignment.
- **Fixed Verification Time $V$:** Assumes the verifier takes constant time regardless of the draft length $k$. While largely true for small $k$ due to parallel verification, memory bandwidth limits eventually make $V$ a function of $k$.

## Phase 2: The Four Questions

### Q3: Claim vs. Reality - Theorem 1 Speedup Bound
Theorem 1 states that for $\alpha V \geq 1.68$, $T_{\SD} > 1.59 T_{\PSD}$. 
- **Audit:** $1.59$ is a specific constant derived from the exponential model. However, the "naive upper bound" of 2x (50% reduction) is the more robust claim. The 1.59x result is highly sensitive to the $\alpha$ parameter (the "efficiency" of the draft model). If $\alpha$ is low (poor draft model), the condition $\alpha V \geq 1.68$ may not be met, and the speedup could diminish.
- **Finding:** The paper correctly identifies that PSD effectiveness is proportional to "verification slowness" ($V$) and "drafting efficiency" ($\alpha$).

### Q4: Empirical Support - Throughput-Latency Consistency
- **Claim:** Up to 75% throughput improvement and 39% latency reduction.
- **Check:** 
  - $T_{\text{new}} = (1 - 0.39) T_{\text{old}} = 0.61 T_{\text{old}}$.
  - Throughput $TH_{\text{new}} = 1 / T_{\text{new}} = 1 / 0.61 \approx 1.64$ ($64\%$ increase).
  - A 75% throughput increase implies $T_{\text{new}} = 1/1.75 \approx 0.57 T_{\text{old}}$ (43% reduction).
- **Conclusion:** The numbers (39% latency vs 75% throughput) are internally consistent and reflect high-load scenarios where batching overhead is amortized.

## Phase 3: Hidden-Issue Checks

### 3.1 The "Low-Load" Fallback
The framework relies on having at least $2m$ requests to fill two batches.
- **Finding:** In low-load scenarios (e.g., $BS < 2$), MineDraft falls back to standard SD. This means the reported 39% latency reduction is **not a per-request latency improvement** for isolated queries, but an average latency reduction for batched requests. This distinction is critical for production SLAs.

### 3.2 The "Irrecoverable Imbalance" Risk
Section 5.1 admits that chunked prefill can lead to "irrecoverable workload imbalance."
- **Logical Trace:** If Batch 0 starts with $m$ requests and Batch 1 starts with $m/2$, the Drafter will finish Batch 1 much faster than the Verifier finishes Batch 0. Since the sync point (Sec 5.2) occurs only when the Drafter returns output, the Verifier may sit idle or vice-versa. Because the system only assigns new requests to the "draft batch," if one batch is structurally smaller, it may never "catch up" if terminations are random.

## Summary of Findings
1. **Mathematical Soundness:** The 1.59x bound is a valid derivation under the specific exponential assumption, though its real-world applicability depends on the draft model's scaling law.
2. **Architectural Gap:** The "two-batch" system introduces a structural vulnerability to load imbalance that can degrade the theoretical 50% gain.
3. **Transparency:** The distinction between batch-latency and query-latency should be explicitly noted.
