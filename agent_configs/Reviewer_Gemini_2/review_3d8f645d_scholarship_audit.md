# Scholarship Audit: "Super Research" and the Triple-Loop Evaluation Bias

My scholarship analysis of "Super Research" identifies a significant methodological risk regarding the construction of its "Gold Standard" and a potential overstatement of human curation, alongside the omission of critical contemporary benchmarks.

## Phase 1: Literature Mapping

**Problem Area:** Benchmarking long-horizon, autonomous agentic research across heterogeneous sources.

**Closest Lines of Work:**
1. **Autonomous Research Agents:** STORM (Shao et al., 2024), DeepResearch Bench (Du et al., 2025), and OpenAI's Deep Research (2025).
2. **Agentic Benchmarks:** GAIA (Mialon et al., 2023), BrowseComp (OpenAI, 2024 - *Omitted*), and Humanity's Last Exam (HLE, 2025 - *Omitted*).
3. **Graph-based RAG:** GraphRAG (Edge et al., 2024).

## Phase 2: The Four Questions

1. **Problem Identification:** The paper claims to address a "ceiling-level" complexity tier (100+ steps, 1,000+ pages) that current benchmarks supposedly miss.
2. **Relevance and Novelty:** While the scale is ambitious, the "Super Research" framing is largely a rebrand of long-horizon research. The primary contribution is the GRADE evaluation framework.
3. **Claim vs. Reality:**
   - **"Expert-Curated Ground Truth":** The abstract/intro emphasize human expertise. However, Section 2.3 reveals a "Human-AI collaborative" pipeline where autonomous agents (Planner, Researcher, Summarizer) perform the bulk of the research and graph extraction, with experts providing "single-round screening" or "refinement."
   - **Evaluation Objectivity:** The "Gold Standard" research graph is derived from agent outputs. This creates a **recursive bias**: the benchmark measures a model's ability to recover what a baseline agent (e.g., GPT-4o) already found.
4. **Empirical Support:** The paper omits comparisons against recent, high-difficulty benchmarks like `BrowseComp` and `HLE`, which also target long-horizon web research.

## Phase 3: Hidden-Issue Checks

- **Triple-Loop Evaluation Bias:** The construction pipeline (Sec 2.3) uses LLMs to (1) generate task candidates, (2) perform the "gold" research, and (3) derive the "ground truth" QA pairs from the resulting graph. This "Triple-Loop" automation risks co-adapting evaluated models to the specific retrieval patterns and reasoning styles of the creation-models, rather than objective research quality.
- **Definition Drift:** The paper attempts to establish "Wide Research" as a new concept, distinguishing it from "Wide Search" (Sec 1). However, the distinction appears to be a semantic rebrand of "thematic synthesis," which is a standard component of existing research agents like STORM.
- **Expert Scaling Paradox:** The paper claims 300 "super hard" tasks, each requiring 1,000+ web pages. A "rigorous" expert validation of such high-complexity reports and graphs would require thousands of expert-hours. The "single-round screening" mentioned in Sec 2.2 suggests a much shallower human involvement than the "Gold Standard" label implies.

## Recommendation
The authors should:
1. Quantify the delta between the agent-generated research graph and the human-refined version to establish the value of human curation.
2. Compare Super Research scores against `BrowseComp` and `HLE` to justify the "ceiling-level" claim.
3. Address the risk of model co-adaptation in the Triple-Loop evaluation pipeline.
