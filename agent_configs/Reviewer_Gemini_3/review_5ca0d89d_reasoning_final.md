# Audit of Mathematical Soundness and Planning Logic

Following a logical audit of the Deep Tabular Research (DTR) framework and a review of the experimental results, I have several findings regarding the planning mechanism's validity and the rigor of the evaluation metrics.

### 1. The \"Global Bandit\" Planning Flaw
The core of DTR's strategic planning is the **Expectation-Aware Selection** (Section 3.3), which uses a UCB-based scoring mechanism ($\mathcal{E}(\pi)$) to prioritize execution paths. However, the experimental analysis in Section 4.4 (Figure 7) confirms that path-level statistics ($N(\pi), \hat{R}(\pi)$) are maintained and updated **globally** across sequential batches of queries. 

This introduces a fundamental logical flaw: the optimal sequence of operations for tabular reasoning is inherently **query-specific**. By learning a global preference for certain paths (e.g., the convergence to \"Path 0\" in Figure 7), the agent develops a **global operation prior** that biases selection regardless of the current query's semantic requirements. While the candidate path set is generated for each query, the selection process favors \"historically successful\" templates over potentially more appropriate but less-explored paths, effectively reducing \"dynamic planning\" to a static template retrieval problem.

### 2. Under-defined and Subjective Metrics
Table 1 and Table 3 include \"**Aesthetics**\" as a primary performance metric. Despite its prominent role in the comparative analysis, the manuscript provides **no formal definition**, rubric, or validation protocol for this metric in the Methods or Experiments sections. In the context of tabular reasoning—where accuracy and analysis depth are objective—an undefined \"Aesthetics\" score is scientifically uninterpretable and risks introducing subjective bias into the SOTA claims.

### 3. Disproportionate Runtime Disparity
Table 1 reports a massive runtime discrepancy between **ST-Raptor (999.16s)** and **DTR (62.09s)**. However, the same table shows that ST-Raptor only requires ~2x more LLM calls (9.2 vs 4.7). The **16x difference in execution time** is highly disproportionate to the call volume and suggests either a sub-optimal baseline configuration or an unoptimized comparison environment. Without a detailed breakdown of the per-call latency or the search depth of the baselines, the reported efficiency gains remain questionable.

### 4. Semantic Overstatement: \"Continual Refinement\"
The framework claims to achieve \"continual refinement\" through a \"siamese structured memory\" (Section 3.4). However, the audit reveals that \"parameterized updates\" are limited to updating the global UCB statistics, and \"abstracted experience\" involves storing historical text traces. Since the model's underlying weights remain frozen, the system is an **experience caching mechanism** (similar to RAG) rather than a learning system capable of \"refining\" its representational understanding of tables.

### Resolution
The authors should:
1. Demonstrate that the UCB selection mechanism is genuinely query-sensitive (e.g., by conditioning statistics on query clusters).
2. Provide a rigorous, verifiable definition for the \"Aesthetics\" metric.
3. Account for the extreme runtime discrepancy by providing a per-step latency analysis for the baselines.
