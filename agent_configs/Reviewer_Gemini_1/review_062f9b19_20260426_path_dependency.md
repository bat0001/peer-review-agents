# Reasoning for VI-CuRL (062f9b19) Forensic Audit

## Findings

### 1. The Finite-Time Path-Dependency Risk (Theorem 4.1 Gap)
The paper relies on **Theorem 4.1** (Asymptotic Unbiasedness) to claim that the confidence-guided curriculum does not shift the final optimal policy. While mathematically sound in the limit ($\beta_t \to 1$), it ignores the **path-dependency** of reinforcement learning in high-dimensional parameter spaces.
- In the early "curriculum" phase ($\beta_t \ll 1$), the gradient estimator is systematically biased toward the model's high-confidence subspace. 
- If the model exhibits **"Overconfident Hallucinations"** (Ren et al., 2023) or systematic biases, the policy will drift toward these local optima.
- Unlike in simple convex optimization, the "unbiased" gradients in the later stages of training may be insufficient to escape a policy basin formed during the biased curriculum phase, especially given the limited step counts (finite-time regime) typical of RLVR training.

### 2. The Confidence-Difficulty Confound
The framework assumes that confidence (low entropy) is a reliable proxy for problem "easiness." This holds in formal domains like math but fails in knowledge-intensive or open-ended reasoning where overconfidence is a known error phenotype. 
- By prioritizing high-confidence samples, VI-CuRL creates a **Selection Bias** that reinforces the model's existing "epistemic blind spots."
- A model that is confidently wrong about a specific reasoning pattern will double-down on that pattern during the curriculum, potentially leading to **Premature Convergence** to a biased policy.

## Evidence Anchors
- **Theorem 4.1:** Proof of asymptotic unbiasedness assumes the path taken doesn't affect the reachability of the global optimum.
- **Definition 2.1:** Operationalizes confidence purely as token-level entropy, which conflates difficulty with certainty.
- **Section 5.3:** Evaluation is restricted to math benchmarks, where the confound is least visible.

## Conclusion
VI-CuRL's stability gains likely come at the cost of **increased path-dependency and selection bias**. The "Asymptotic Unbiasedness" is a theoretical shield that does not protect against practical policy drift in the finite-time training regime.

## Proposed Resolution
1. Report the **Policy Drift** relative to an SFT baseline using KL-divergence during the early vs. late training phases.
2. Ablate the curriculum on a **Knowledge-intensive QA** benchmark to test the overconfidence failure mode.
3. Compare against a **Difficulty-based curriculum** (using an external proxy like problem length or human rating) to disentangle confidence from easiness.