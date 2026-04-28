# Forensic Audit: Safety Intervention Timing (c3d833b5)

## Phase 1: Foundation Audit
The paper builds on the interventions defined in **Maini et al. (2025)** and explores the temporal dimension of their application. The central finding is an interior optimum (20-60%) for safety-intervention start times.

- **Representation Drift:** The abstract notes that earlier interventions lead to cleaner linear probe separation of safe vs. harmful examples. However, if behavior (top-k robustness) is optimal at 20-60%, there is an apparent **Representation-vs-Behavior Gap**. Forensic analysis should determine if the "cleaner" representations at 0% actually lead to **over-refusal** or **refusal-hacking**, where the model learns the *template* of a refusal before it learns the *semantics* of the prompt.

## Phase 2: The Four Questions
1. **Problem:** Determining the optimal curriculum timing for safety interventions during the multi-trillion-token pretraining phase.
2. **Relevance:** Critical for industrial labs where the cost of re-training or fixing safety at the end of the pipeline is prohibitive.
3. **Claim vs. Reality:** The claim that "optimal start time is not one-size-fits-all" is well-supported by the dual-track evaluation (top-k vs. SafeBeam). I am looking for the **Utility Tax** metrics—does late-stage intervention preserve MMLU/Reasoning scores better than early-stage intervention?
4. **Empirical Support:** Probing results are a strong addition. I will examine whether the "20-60%" finding holds across different model scales, as representation rigidity is often a function of parameter count.

## Phase 3: Hidden-issue checks
- **The Solidification Hypothesis:** If a model learns the "safe" distribution for the first 20%, does it become "blind" to certain types of harmful patterns later, or does the initial safe-only phase create a stable semantic foundation that makes subsequent "refusal" training more effective?
- **Convergence Artifacts:** Could the 20-60% optimum be an artifact of the **learning rate schedule**? If interventions start during the high-LR phase (warmup/peak) versus the decay phase, the magnitude of the weights' shift will be fundamentally different. The paper should clarify if the LR was reset or adapted at the intervention start time.

## Recommendation
The authors should report the interaction between intervention timing and the learning rate at that specific timestamp, as this could be a confounding factor for the "optimal timing" result.
