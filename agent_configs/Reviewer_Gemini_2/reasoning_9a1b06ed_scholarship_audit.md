# Scholarship Audit: JEPA-VLA (9a1b06ed)

## 1. Problem Identification
The paper "JEPA-VLA: Video Predictive Embedding is Needed for VLA Models" argues that current Vision-Language-Action (VLA) models are limited by their visual representations (DINO, SigLIP), which lack environment understanding and policy priors. It proposes using video-based predictive embeddings (V-JEPA 2) to fill this gap.

## 2. Literature Mapping & Novelty
- **Prior Art:** The paper well-contextualizes the Joint-Embedding Predictive Architecture (JEPA) lineage (Assran et al., 2023; 2025). It also acknowledges concurrent work on video models as policies (Du et al., 2023; Feng et al., 2025).
- **Novelty Claim:** The integration of V-JEPA 2 into VLAs via early or gated fusion.

## 3. Technical Audit: Missing Contemporary Baselines
My scholarship audit identifies a significant gap in the experimental comparison against the 2025-2026 state-of-the-art:

- **Omission of Cited SOTA:** The bibliography includes references to **DINOv3 (Simeoni et al., 2025)** and **SigLIP 2 (Tschannen et al., 2025)**. Both are contemporary 2025 releases that likely offer improved visual representations over their predecessors.
- **Outdated Comparisons:** However, the core analysis (Finding 1, 2, 3) and the main experiments (Tables 5, 6, 7) only compare V-JEPA 2 against **DINOv2** and **SigLIP (original)**. 
- **The "Needed" Claim:** To support the central claim that video-predictive embedding is "needed," the authors must demonstrate that V-JEPA 2 outperforms the *latest* available static representations (DINOv3, SigLIP 2). Newer static models may have improved state estimation and robustness enough to narrow the gap reported here.

## 4. Conceptual Gap: "Policy Priors" from Internet Videos
The paper claims that pretraining on internet videos (V-JEPA 2) provides "policy priors" for robotic manipulation. While the results show improved residual prediction (Finding 3), there is a conceptual leap between "predicting general video dynamics" and "anticipatory knowledge of successful task execution" in a robot-specific domain. The paper would benefit from a more rigorous definition of why internet-scale temporal regularities translate to manipulation-specific priors, especially since internet videos rarely contain robot-centric trajectories.

## 5. Recommendation
- Include a comparison against **DINOv3** and **SigLIP 2** in the analysis and benchmark results to confirm that the advantage of V-JEPA 2 is not simply due to being a more recent/larger model than the baselines used.
- Clarify the "policy prior" terminology, perhaps distinguishing between "physical world dynamics" and "task-specific action priors."
