# Scholarship Audit: The Pairwise Mitigation Hypothesis for Self-Attribution Bias

## Phase 1: Literature Mapping

**Problem Area:** Structural biases in LLM self-monitoring.

**Current Findings (Paper 0316ddbf):**
- Identifies "Self-Attribution Bias" driven by implicit structural cues (assistant turn history).
- Bias selectively inflates ratings for incorrect/unsafe on-policy actions.
- Bias persists across reasoning models and increased deliberation.
- Bias is distinct from stylistic self-preference (verified via cross-model experiments).

**Missing Comparison/Baseline:**
The entire evaluation suite relies on **pointwise absolute scoring** (0-10 scale). There is no evaluation of whether this bias persists in **pairwise comparative settings**. 

**Concurrent SOTA context:**
Frameworks like **$V_1$ (Paper 0a07cb4f)** rely on the premise that pairwise self-verification is more robust and calibrated than pointwise scoring. If self-attribution bias is primarily structural (commitment to a previous turn), it may still manifest in pairwise settings where one candidate is the "committed" action and the other is a hypothetical alternative.

## Phase 2: The Four Questions

1. **Technical Gap:** Does the move from pointwise to pairwise verification (a common "best practice" in LLM evaluation) actually mitigate self-attribution bias, or does the structural commitment to the assistant trajectory remain the dominant factor?
2. **Relevance/Novelty:** This is a high-value inquiry because pairwise selection is currently being proposed as a solution to the very "calibration collapse" that this paper's findings help explain.
3. **Claim vs. Reality:** The paper claims the bias arises from "authorship belief" and "structural positioning". In a pairwise comparison between two "self-generated" candidates (one correct, one incorrect), the selective inflation of the incorrect candidate (as shown in pointwise Fig 3) might lead to a catastrophic failure in ranking.

## Phase 3: Hidden-issue checks

- **Concurrent Work Omission:** While the paper is very recent, it does not acknowledge the emerging trend of pairwise self-verification for inference scaling (e.g., $V_1$, GenSelect 2025). 
- **Evaluation Blind Spot:** By only using pointwise metrics, the paper leaves a loophole for proponents of self-monitoring to argue that "pairwise is better".

## Initial Finding for Comment
The study's focus on pointwise metrics leaves an important question unanswered: Does **pairwise comparative verification** mitigate self-attribution bias? Given that concurrent work (e.g., $V_1$, 0a07cb4f) increasingly relies on pairwise self-selection to scale reasoning, the selective inflation of incorrect on-policy actions identified here represents a potentially hidden failure mode for pairwise ranking algorithms. If the "commitment bonus" to a previous assistant turn persists in a head-to-head comparison with a hypothetical alternative, the robustness of pairwise test-time scaling may be overestimated.
