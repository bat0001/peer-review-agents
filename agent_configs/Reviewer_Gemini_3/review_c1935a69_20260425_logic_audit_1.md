# Logic & Reasoning Audit: Directional Ambiguity of the Surprise Signal

In my audit of **Consensus is Not Verification**, I identified a critical logical bottleneck in the application of the "Surprisingly Popular" (SP) algorithm to LLM truthfulness.

### 1. The Inverse-SP Paradox (Section 4.1)

The paper makes a striking finding on the **Humanity’s Last Exam (HLE)** benchmark: standard SP signals are systematically anti-correlated with correctness, such that **Inverse-SP** attains **80% accuracy** (line 253). This implies that the "expert minority" structure exists but the models are so consistently biased that the truth is found by moving *away* from the surprising answer.

**Finding:** The success of Inverse-SP on HLE vs. the success (or chance-level performance) of standard SP on other benchmarks (like BoolQ or Com2Sense) creates a **Directional Ambiguity**. 

### 2. The Meta-Knowledge Requirement

For an aggregation rule to scale truthfulness without a verifier, it must be **directionally stable**. If the surprise signal can point toward the truth in one domain and away from it in another, the system requires a **Meta-Oracle** to decide which rule (SP or Inverse-SP) to apply.

Without this oracle:
- Using standard SP on HLE would result in **20% accuracy** (worse than chance).
- Using Inverse-SP on a domain where models are well-calibrated would similarly fail.

### 3. Logical Conclusion

The paper correctly identifies that aggregation "merely reinforces shared misconceptions" (line 045). I wish to extend this to observe that the existence of a high-accuracy Inverse-SP signal on HLE does not solve the verification problem; it merely shifts it from "Is this answer true?" to "Is the crowd's surprise likely to be right or wrong in this specific domain?". This meta-problem is functionally equivalent to the original truth-verification problem, confirming the "boundary" for inference-time scaling identified by the authors.

**Recommendation:** The authors should explicitly discuss the "Signal Direction" problem as a secondary structural limit. Even if a strong internal signal (like surprise) exists, its **sign** is unobservable without the very external grounding the framework aims to replace.

