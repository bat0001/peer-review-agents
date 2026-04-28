# Forensic Audit: Tool-Genesis Benchmark

**Paper ID:** 640e44ec-91da-4d38-9b9a-4a3a20ad15d0
**Title:** Tool-Genesis: A Task-Driven Tool Creation Benchmark for Self-Evolving Language Agent
**Status:** in_review

## Phase 1: Foundation Audit

### 1.1 Citation Audit
The paper's bibliography is current, featuring several 2025 and 2026 citations (e.g., TM-Bench, SciEvo). It correctly acknowledges seminal works in the tool-use space (Toolformer, ReAct).
- **Filler Ratio:** Low.
- **Misattribution Check:** No major issues found, though the heavy reliance on Toucan (Xu et al., 2025) for data construction is noted.

### 1.2 Novelty Verification
The paper claims novelty in generating "toolsets" using the Model Context Protocol (MCP). However, it omits several 2025 benchmarks from its primary comparison table (Table 1), such as **ToolCoder** and **ToolHop**, which are only mentioned in Figure 3.

### 1.3 Code-Paper Match
No public repository is linked in the paper (likely due to double-blind constraints), though a project page URL is provided. This limits verification of the claimed 86 executable MCP servers.

---

## Phase 2: The Four Questions

### 2.1 Problem Identification
The paper aims to decouple tool generation from tool utilization to solve the "black box" diagnostic problem in existing benchmarks.

### 2.2 Relevance and Novelty
While requirement-driven tool creation is highly relevant, the novelty is partially overstated by omitting direct feature-by-feature comparisons with the latest 2025 baselines.

### 2.3 Claim vs. Reality (Forensic Weaknesses)
- **Mathematical Error in Eq 15:** The "Oracle-Normalized Success Rate" is defined as $SR_j = \frac{1 - s_{gt}}{1 - s_{gen} + \epsilon}$ (Line 703). This formula is mathematically nonsensical for a success rate. If the ground-truth (oracle) success $s_{gt}$ is 1.0 (perfect), the numerator becomes 0, resulting in a score of 0 regardless of the generated tool's quality. If $s_{gt}$ is success, this formula measures something closer to an "inverse error ratio," but even then, it would penalize high $s_{gen}$ (success of the generated tool).
- **Evaluation Circularity:** Level 3 functional correctness relies on LLM-synthesized unit tests when extraction fails (Line 218). This creates a risk that models are being tested on the same biases as the test generator.

### 2.4 Empirical Support
The Code-Agent repair loop results (Table 2) show significant gains, proving that execution feedback is load-bearing. However, the $SR$ values in Table 2 are suspect given the flawed formula in Eq 15.

---

## Phase 3: Hidden-Issue Checks

- **Logical Consistency:** The contradiction between the stated goal of "Success Rate" and the "Error-like" formula in Eq 15 is a major consistency break.
- **Overclaim Analysis:** The term "Self-Evolving" in the title and abstract is not supported by the experimental setup, which only evaluates a fixed iterative repair loop for a single task. There is no session-over-session growth or model adaptation.

## Final Finding Summary
The paper introduces a timely MCP-based benchmark, but the load-bearing utility metric (Eq 15) is mathematically broken, and the evaluation relies on circular LLM-generated tests. The "Self-Evolving" framing is a significant overclaim.

**Provisional Score:** 3.0 (Weak Reject) due to metric invalidity.
