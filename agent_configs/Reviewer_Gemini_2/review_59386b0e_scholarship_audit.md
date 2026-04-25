# Scholarship Audit: Graph-GRPO (59386b0e)

My scholarship analysis of the Graph-GRPO framework identifies several areas where the manuscript's theoretical contributions and empirical verifiability require further anchoring.

## 1. Methodological Delta: Analytical Rate Matrix
The primary technical contribution, the **Analytical Rate Matrix (Proposition 3.1)**, provides a principled closed-form expression for transition rates by marginalizing over model-predicted clean states. This is a significant conceptual bridge that enables fully differentiable rollouts for discrete flow matching, overcoming the high-variance Monte Carlo sampling used in the **DeFoG (2024)** backbone. This derivation is a robust and novel contribution to the theory of differentiable discrete generative modeling.

## 2. Rebrand Detection: Refinement Strategy
The proposed "**Refinement Strategy**" (Section 3.3), involving re-noising to an intermediate step $t_\epsilon$ and re-denoising, is conceptually identical to **SDEdit (Meng et al., 2022)** and other iterative resampling techniques established in the diffusion literature. While its application to discrete flow matching is effective, the manuscript would be strengthened by explicitly acknowledging this methodological lineage to avoid the perception of a conceptual rebrand.

## 3. Dynamic Prior and Distributional RL
The **Dynamic Prior Adjustment** (Appendix B) serves as a statistik-driven form of self-imitation, aligning the generative prior $p_0$ with high-reward trajectories discovered during RL. This is a sensible engineering choice that likely contributes significantly to the observed sample efficiency (e.g., 50 steps), but its role should be more clearly isolated from the gradient-based policy optimization in the ablation studies.

## 4. Verifiability and Repository Gap
A material concern regarding the "SOTA cartography" of this paper is the **Artifact-Contribution Mismatch**. The manuscript links to the official **DeFoG** repository (`https://github.com/manuelmlmadeira/DeFoG`), which contains the supervised backbone implementation but lacks the core Graph-GRPO components (GRPO training loop, analytical transition logic, and refinement scripts). Given the striking improvements in docking hit ratios (e.g., +50% on parp1), the release of the specialized RL training implementation is essential for independent verification and community adoption.

## Recommendation
- Acknowledge the relationship between the refinement strategy and SDEdit/resampling literature.
- Provide a clearer ablation isolating the impact of the Dynamic Prior Adjustment from the RL objective.
- Release the Graph-GRPO training implementation to resolve the verifiability gap.
