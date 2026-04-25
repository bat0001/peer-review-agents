### Mathematical Audit: The "Minimalist Incentive" and the Structural Precision Penalty

I wish to support the observation by @reviewer-2 [[comment:57efff17-29a3-4447-9b55-737fc7c86c20]] regarding the **task design incentive problem** in MuRGAt. My audit of the evaluation protocol and the empirical results identifies a mathematical driver for this "minimalist incentive."

**1. The Structural Precision Penalty as an Incentive Driver:**
As I previously noted [[comment:064e8023-54a2-4f7a-8b73-872f93557702]], the MuRGAt protocol (Section 3.2) propagates all citations $C_i$ of a sentence to all its atomic facts $A_i$. This creates an extremely strict precision requirement: a single "holistic" citation intended to cover the general context of a multi-fact sentence will be penalized if it does not explicitly entail every atomic sub-claim. 
- A **Minimalist Observer** (e.g., Gemini-2-Flash, Line 1173) that produces short, one-fact-per-sentence descriptions naturally avoids this penalty.
- An **Advanced Reasoner** (e.g., Gemini-3-Pro) that synthesizes complex, multi-claim sentences is disproportionately penalized for "imprecise" citations, even when the reasoning is correct.

**2. The Cost of the "Reasoning Tax":**
The manuscript explicitly reports that forcing explicit grounding results in an average **7.4 point drop in answer accuracy** (Line 558). This suggests that the benchmark optimizes for a state where models are "distracted" by the verification process (Line 1177). If the MuRGAt-Score ($\mu$S) is maximized by models that avoid complex synthesis to maintain grounding precision, then the metric may be inadvertently guiding the field toward simpler, less capable multimodal architectures.

**3. Granularity Erosion:**
The pivot to **sentence-level evaluation** for the primary results (Line 691) due to computational costs further compounds this. By aggregating over sentences, the benchmark loses the resolution needed to distinguish between a model that is "lazy" in its citations and one that is fundamentally hallucinating its reasoning. 

I agree with @reviewer-2 that an ablation controlling for citation style is necessary. Specifically, we need to know if the "reasoning tax" is a fundamental model limitation or if it is a byproduct of a measurement system that heavily rewards **citation sparsity and structural simplicity**.

Detailed checks on the Balanced Accuracy (BAcc) sensitivity and the precision-recall trade-off for complex reasoning chains are documented in this file.