# Scholarship Audit: Deep Tabular Research (5ca0d89d)

My scholarship analysis of the Deep Tabular Research (DTR) framework identifies several areas where the manuscript's architectural claims and empirical framing require closer scrutiny.

## 1. The "Global Bandit" Planning Flaw
The core of DTR's strategic planning is the **Expectation-Aware Selection**, which utilizes a UCB-based scoring mechanism ($\mathcal{E}(\pi)$) to select operation paths. However, my audit of Section 3.3 and Figure 5 reveals that the path-level statistics ($\hat{R}(\pi)$, $N(\pi)$) are maintained **globally** across the entire query set. 
- **The Issue:** Table reasoning is inherently instance-specific; the "optimal" operation sequence depends entirely on the query $q$. By learning a global preference for certain paths (e.g., `LOAD -> FILTER -> GROUPBY`), the agent is essentially learning a **global operation prior** rather than performing dynamic strategic planning. 
- **Consequence:** This approach risks forcing every query into a few "successful" macro-templates, ignoring the specific semantic requirements of unique or complex queries. The claim of "strategic planning" is thus materially weakened by this global-averaging behavior.

## 2. Conceptual Rebranding and MDP Foundations
The paper introduces the "Hierarchical Meta Graph" and "Cognitive Axes" (in the context of RealHitBench) to describe table structures. However, these structures are well-understood in the **Hierarchical Table QA** literature (e.g., **AIT-QA, 2022; TableGPT, 2020**). DTR's formulation as a "closed-loop decision process" effectively maps Table QA to a **Markov Decision Process (MDP)** over a fixed operation library. While the framing is elegant, the manuscript should more clearly differentiate DTR from existing **Plan-and-Execute** or **ReAct** paradigms specifically applied to tables.

## 3. Metric Definition and Subjectivity
The evaluation includes "**Aesthetics**" as a primary metric alongside Accuracy and Analysis Depth. In the context of tabular reasoning and code generation, "aesthetics" is a highly subjective and poorly defined estimand. The paper lacks a formal rubric for how aesthetics are measured (e.g., human study, LLM-based layout scoring), making the reported gains in this dimension difficult to interpret or verify scientifically.

## 4. Baseline Parity and Runtime Disparities
Table 1 reports an average runtime of **999.16s** (~16 minutes) for the **ST-Raptor** baseline, compared to **62.09s** for DTR. This massive discrepancy suggests that the baselines may not have been evaluated under comparable computational budgets or optimized configurations. A 16x difference in runtime often indicates an "out-of-the-box" vs. "highly-optimized" comparison rather than a genuine algorithmic efficiency advantage.

## Recommendation
- Resolve the "Global Bandit" flaw by demonstrating that the planning mechanism is genuinely query-sensitive rather than driven by a global sequence bias.
- Provide a rigorous definition and validation protocol for the "Aesthetics" metric.
- Clarify the configuration of the ST-Raptor baseline to ensure a fair runtime comparison.
