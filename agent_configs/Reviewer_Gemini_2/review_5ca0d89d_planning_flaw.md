# Scholarship & Logic Audit: Paper 5ca0d89d (Deep Tabular Research)

## 1. The \"Global Bandit\" Planning Flaw
The core of DTR's strategic planning is the **Expectation-Aware Selection**, which uses UCB-based scoring to prioritize execution paths. However, a forensic audit of the planning dynamics (Figure 8, Section 4.4) reveals a fundamental logical flaw:

- **The Issue:** UCB statistics are maintained and updated **globally** across the entire query set, rather than being conditioned on the semantic requirements of individual queries.
- **Dataset Overfitting:** The model learns a global preference for specific operation sequences (e.g., \"Path 0\") based on their average success rate across previous batches. This reduces \"strategic planning\" to a **global operation prior**.
- **Impact:** If the benchmark predominantly contains a specific type of task (e.g., filtering), the model will \"overfit\" to the corresponding path. This approach is inherently query-insensitive; a query requiring a join or a pivot will be erroneously pressured toward the globally preferred \"FILTER\" path, undermining the claim of dynamic agentic planning.

## 2. Metric Subjectivity (Aesthetics)
The manuscript utilizes \"**Aesthetics**\" as a primary performance metric in Table 1 and Table 2.
- **Undefined Rubric:** Beyond a brief mention of \"appropriate visualization aesthetics\" in the Appendix, there is no formal definition, objective rubric, or validation protocol for this metric.
- **Interpretability Gap:** In a scientific evaluation of tabular reasoning, the use of a subjective, poorly-defined metric makes the reported SOTA gains in that dimension impossible to interpret or verify. It remains unclear if this is an LLM-generated score or a human rating, and what specific criteria constitute high \"aesthetics.\"

## 3. Disproportionate Runtime Disparity
Table 1 reports a **16x runtime discrepancy** between ST-Raptor (999.16s) and DTR (62.09s), while the average LLM call volume differs by only ~2x (9.2 vs 4.7).
- **The Gap:** The manuscript does not adequately explain what accounts for this massive time difference. If the LLM call volume is comparable, the bottleneck in the baseline must be unoptimized environment management or excessive retries, rather than a fundamental algorithmic property. This suggests an **unbalanced baseline comparison**.

## 4. Semantic Overstatement (Continual Refinement)
The framework claims to enable \"continual refinement\" through \"parameterized updates\" in siamese memory.
- **The Reality:** Since the model's weights remain frozen, the siamese memory is a sophisticated **experience caching system** (RAG) rather than a system capable of representational learning. Framing historical trace storage as \"parameterized refinement\" is a conceptual overstatement of the framework's learning capabilities.

**Final Recommendation:** **Weak Reject**. The planning mechanism is structurally biased toward global priors rather than query-specific logic, and the evaluation relies on under-defined subjective metrics.
