# Forensic Audit: Statsformer: Validated Ensemble Learning with LLM-Derived Semantic Priors

## Finding: Discrepancy in "One-Time" Prior Elicitation and Context Batching Reality

Statsformer is presented as a cost-effective framework that uses an LLM "only once" to elicit semantic priors. However, the technical implementation details in the appendix reveal a more complex batching requirement for high-dimensional datasets that challenges this efficiency narrative.

### Evidence
- **Abstract (page 1):** "Statsformer uses an LLM only once to elicit priors... making it efficient."
- **Section D.1 (page 24):** The authors admit that "To reduce the LLM context length required for large feature sets, we divide the feature names into at most $\sqrt{p}$ batches and perform one API query per batch." 
- **Scalability (page 24):** For a dataset with 1,000 features, the paper reports a cost of $2.80 and 15 minutes of querying time. While modest, this is not a "single query" operation for the scales often encountered in tabular genomics or web analytics.

### Impact
The "only once" claim is a central selling point for the framework's scalability. While the batching strategy is a sound engineering response to context window limits, the main text should be more transparent about the linear or sub-linear scaling of query counts with respect to the feature dimension $p$. For extremely high-dimensional problems ($p > 10^5$), the "one-time" cost could become a non-trivial bottleneck.

### Proposal for Resolution
The authors should:
1. Revise the efficiency claim in the Abstract and Intro to reflect that elicitation is a "one-time pre-processing stage" rather than a "single LLM call," especially for high-dimensional settings.
2. Provide a more detailed breakdown of how the $\sqrt{p}$ batching rule was derived and whether it remains optimal across different LLM provider context limits.
3. Clarify the impact of batching on the "semantic consistency" of the priors—i.e., whether the LLM provides different relative scores when features are presented in isolation versus in a larger context.
