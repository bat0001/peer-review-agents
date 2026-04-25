# Scholarship Audit: Task-Level Model-Merging Collapse

## Phase 1: Literature Mapping

**Problem Area:** Catastrophic performance degradation in model merging (Merging Collapse).

**Closest Prior Work:**
1. **TIES-Merging (Yadav et al., 2024):** Focuses on parameter-space conflicts (sign interference).
2. **DARE (Yu et al., 2024):** Aims to mitigate interference by pruning weight updates.
3. **RobustMerge (Zeng et al., 2025):** Identifies "Directional Collapse" in representation space.
4. **Zipit! (Stoica et al., 2024):** Focuses on feature alignment to enable merging models from different training trajectories.

**Gaps in Actionability:**
The paper argues that representational incompatibility is the primary driver of collapse. However, as noted by the community, this metric is currently only calculated **post-merge**, making it useless for pre-merge screening.

## Phase 2: The Four Questions

1. **Technical Gap:** Can we predict "Merging Collapse" before performing the merge? The paper provides a descriptive "Merging Difficulty Score" (MDS) but fails to validate it as a predictive tool using pre-merge signals like CKA or weight-space KL divergence.
2. **Relevance/Novelty:** The RDT-based theoretical bound is novel in the merging context but lacks anchoring to recent LLM-specific RDT work (e.g., Young et al., 2025).
3. **Claim vs. Reality:**
   - Claim: Representational incompatibility is the main driver.
   - Counter-argument: If Zipit!-style alignment can resolve this incompatibility, then the "Collapse" is a failure of the merging method (alignment), not a fundamental task limit.
4. **Empirical Support:** The use of "Lots-of-LoRAs" (Mistral-7B) is excellent and provides high-diversity evidence.

## Initial Finding for Comment
The paper identifies a critical "prediction deadlock": representational incompatibility is a superior predictor of collapse, but it is currently only measurable post-merge. Integrating pre-merge signals like **Centered Kernel Alignment (CKA)** or exploring the mitigation potential of **feature alignment (e.g., Zipit!)** would transform the contribution from a post-hoc diagnostic to a practical engineering framework.
