# Forensic Audit of "GFlowPO: Generative Flow Network for Prompt Optimization"

## Phase 2.4 — Empirical Support & Baseline Parity

**Finding: Sample Efficiency vs. Total Target-LM Budget**

The paper claims that GFlowPO is "sample-efficient" due to its off-policy GFlowNet objective and replay-based training. In the context of prompt optimization, the primary "sample cost" is the number of calls to the **Target-LM** (the model being prompted), which is often a large, expensive API (e.g., GPT-4).

**Forensic Point:**
When reporting gains over "recent discrete prompt optimization baselines," is the **total number of Target-LM evaluations** strictly controlled? 
1.  If GFlowPO evaluates thousands of prompts during the "off-policy" phase while baselines like simple Greedy Search or EVO-Prompt are limited to a few hundred, the comparison is confounded by search budget.
2.  The paper should report a **Search Efficiency Curve** (Accuracy vs. Target-LM Calls) to establish whether the GFlowNet framing provides a higher "yield" per expensive evaluation than simple iterative refinement.

**Contribution Gap:**
Does the method consider the **Transferability of optimized prompts**? Often, prompts optimized for a lightweight model (used in the GFlowNet loop) do not generalize to the Target-LM. If GFlowPO requires a Target-LM call for every GFlowNet update, the efficiency gain of GFlowNet is partially neutralized by the evaluation bottleneck.

## Phase 3 — Hidden-issue checks

**Dynamic Memory Update (DMU) and Exploration Collapse:**
The DMU mechanism updates the meta-prompt by injecting "top-performing prompts from a small priority queue." Forensically, this resembles **Positive Reinforcement** in evolutionary strategies, which is known to cause **Exploration Collapse**. 
1.  If the meta-prompt becomes dominated by the current global optimum, does the GFlowNet's "diverse sampling" property (its main theoretical advantage) vanish? 
2.  The authors should provide an **Entropy Audit** of the GFlowNet policy over time with and without DMU to prove that diversity is actually preserved in the presence of the concentrated meta-prompt.
