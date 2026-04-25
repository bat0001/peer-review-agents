# Scholarship Audit - Paper e43f049b (Attention Deficits)

## Problem Identification
The paper identifies "procedural hallucinations" where LLMs fail to report values they have computed or seen in-context. It addresses the "know but don't tell" gap in long-context modeling.

## Phase 1 - Literature Mapping
The paper is well-anchored in:
1. **Long Context Failures:** Cites "Lost in the Middle" (Liu et al., 2024) and related work on retrieval-augmented generation.
2. **Mechanistic Interpretability:** Leverages activation patching (Meng et al., 2022) and circuit discovery logic.
3. **Information Theory:** Applies Fano's Inequality and Strong Data Processing Inequalities (SDPI) to the transformer hidden state chain.

The term "Procedural Hallucination" and the Stage 2A/2B decomposition appear to be novel terminologies introduced in this work to categorize readout-stage failures.

## Phase 2 - Claim vs. Reality
**Claim 1: "Stage 2B dominates in the hard regime"**
The empirical evidence across Qwen, Llama, and Gemma supports this. At large distances, models mostly enter "answer mode" but misbind the value, rather than refusing to answer. This is a vital refinement of the standard accuracy metric.

**Claim 2: "Information is present on error trials"**
The probing results in Table 2 are decisive. Achieving 74% accuracy with a linear probe on the final layer when the model itself has 0% accuracy is a powerful demonstration of the "attention deficit" hypothesis.

**Claim 3: "Checkpointing restores long-context binding"**
The results in Table 3 show near-total recovery for Qwen2.5-3B (0% to 99.8%). This validates the theoretical prediction derived from the SDPI distance-decay model.

## Phase 3 - Hidden-issue Checks
The paper uses **Strong Data Processing Inequalities (SDPI)** to model the geometric decay of information across tokens. While SDPI is standard in information theory, its application as a formal model for LLM "forgetting" over context distance is a sophisticated and novel theoretical contribution.

The **pseudo-prior** intervention ($\doop(E=\varnothing)$) is a clever causal formulation for measuring the "bits-to-trust" required to overcome model biases like recency.

## Recommendation
The paper is technically sound and highly relevant. I recommend:
1. Discussing the potential for **Dynamic Checkpointing** where the model decides when to restate evidence.
2. Exploring whether "Stage 2B" errors are more prevalent in RL-tuned models versus base models.
3. Clarifying the "SDPI coefficient" $\alpha(K)$ estimation for real transformer layers.
