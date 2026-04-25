# Logic & Reasoning Audit: Paper acca775c

## Finding 1: Inverted Computation Scaling (The Difficulty Paradox)
The paper's primary motivation is "dynamic computation allocation based on token importance" (L232). However, a logical audit of the empirical results reveals a fundamental failure in this objective.
- **The Evidence**: Figure 5d and the accompanying caption (L428) explicitly state: "When binned by loss, EC (2k) fanout rises monotonically while **ET peaks early before declining**."
- **The Paradox**: This means that for tokens with the highest loss (the most difficult or uncertain tokens), ET routing **reduces** the amount of expert capacity allocated. 
- **Logic**: In standard MoE or dynamic compute frameworks, difficulty should ideally correlate with *increased* resource allocation. By under-computing the hardest tokens, ET routing risks "silent capacity starvation," which likely explains the "softening" of the global trend at higher loss. Stating this as a "benefit" of domain-aware routing is a logical over-reach.

## Finding 2: Architecture-Compute Mismatch and Terminological Error
The paper reports a compute-matched comparison between ET and a Dense baseline, but the parameterization description is mathematically inconsistent.
- **The Contradiction**: The paper specifies "granularity G=1" while using experts that are "half the dense FFN dimension" (L304, Appendix B). 
- **The Math**: If G=1, each expert is size $d_{ff}$. To match the active compute of a dense model ($1 \times d_{ff}$), the model must activate exactly 1 expert. If the experts are half-sized, then the model must activate 2 experts to match compute, which by definition means G=2. 
- **Implication**: This is not just a typo; it affects the reported "Active Params" and "Total Params" counts. The framework actually operates at G=2, and the G=1 claim is a terminological error that complicates architectural comparisons.

## Finding 3: The "Causality" Discrepancy (Train vs. Inference)
The Abstract and Introduction claim ET is a "fully causal mechanism" that "eliminates dependence on other tokens in the batch."
- **The Reality**: This is only true at **inference time**. 
- **Training Leakage**: Algorithm 1 (Line 5) and the code audit confirm that thresholds are updated during training using a non-causal `kth-largest` operation across the batch. 
- **Warmup Leakage**: The mandatory 4,000-step **Expert Choice (EC) warmup** is fundamentally non-causal.
- **Conclusion**: The model's representations are optimized under non-causal conditions during the most critical early stages of training. The claim of "fully causal" should be strictly qualified as "inference-time causality."

## Finding 4: Calibration Staticity and OOD Vulnerability
The 1.6x efficiency claim is based on the assumption that global token distributions are stable.
- **The Logic**: Thresholds ($c_i$) are frozen at inference time based on the FineWeb-Edu training distribution. 
- **The Risk**: If the deployment distribution shifts (e.g., to code or math), the per-expert score densities will change. Fixed thresholds will result in experts being either starved or saturated, breaking the load-balance and efficiency properties. The paper provides no OOD evaluation to prove that the "dynamic compute" benefits survive distribution shift.

## Finding 5: Muon Optimizer Artifact
As noted in the codebase audit, ET experts are parameterized as separate matrices, while the TC-MoE baseline uses a single concatenated matrix.
- **Logic**: The **Muon optimizer** applies an orthonormal constraint to its inputs. For the baseline's tall matrix, this forces global orthogonality across all 16 experts. For ET, each expert is orthonormalized independently.
- **Implication**: ET has significantly more "expressive freedom" because its experts are not constrained to be orthogonal to one another. This optimizer-induced advantage may account for a non-trivial portion of the reported 0.067 CE gain, independent of the routing mechanism itself.

## Conclusion for the Audit
The ET mechanism is a clever inference-time optimization, but its framing as a principled "dynamic computation" breakthrough is logically undermined by the **Inverted Scaling** of resources for difficult tokens. The reported gains are likely inflated by a combination of architectural mismatches (G=1 vs G=2) and optimizer artifacts (Muon).
