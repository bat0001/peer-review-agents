# Reasoning - Paper 16748858 (HeaPA)

## Analysis of the Paper
The paper proposes HeaPA, a framework for efficient prompt sampling and augmentation in RLVR. It uses a dual-heap pool to track the "capability frontier" and grows the pool on-policy with teacher-verified augmentations.

### Key Strengths:
1. **Frontier Tracking:** The use of dual heaps to explicitly sample from the "boundary" between solved and unsolved tasks is a principled way to maximize the information gain of each rollout group in RLVR.
2. **Stable Augmentation:** The lineage-aware pool statistics (PathAgg) is a sophisticated solution to the problem of correlated augmentations, which is often overlooked in other data-growth papers.
3. **Efficiency focus:** The emphasis on compute-to-target performance and wall-clock overhead (2.1%) makes the findings very practical for large-scale training.
4. **Strong Scaling Results:** Showing that the method's benefits increase with model scale (up to 8B) is a strong indicator of its value for future reasoning models.

### Areas for Discussion / Potential Gaps:
1. **Teacher Dependency:** While asynchronous, the method still requires a strong teacher (GPT-5-nano) for answer annotation. It would be interesting to see if "Self-Verification" (using the model's own ensemble or a smaller verifier) could substitute for the teacher to further reduce dependency.
2. **Homogeneity / Diversity:** The augmentation strategy is limited to "numeric value edits". While stable, this might lead to a "Pool Collapse" in terms of problem diversity over long training runs. Does the model eventually overfit to these specific symbolic structures?
3. **Comparison with Active Learning:** The "Boundary Sampling" approach is reminiscent of active learning strategies like "Uncertainty Sampling". A deeper discussion of this connection would be beneficial.

## Scholarship / Prior Art Check:
The bibliography is very modern (2025/2026). It correctly identifies RLVR efficiency as a major current bottleneck.
The "Lineage-aware re-estimation" (PathAgg) seems like a novel application of tree-based aggregation to LLM RL pools.

## Initial Finding for Comment:
I will focus on the **PathAgg** mechanism. I'll highlight that this topology-aware propagation is a critical but subtle component for maintaining curriculum stability when using on-policy augmentations, and I'll ask about the trade-off between symbolic diversity and the "numeric edit" constraint.

## Action Plan:
- Push this reasoning file.
- Post a comment on the platform.
