# Scholarship Audit: RetroReasoner (b29aad52)

My scholarship analysis of the RetroReasoner framework identifies several areas where the manuscript's architectural claims and methodological positioning relative to both chemical and ML literature require further anchoring.

## 1. Methodological Heritage: Corey's Logic
The paper introduces the "SyntheticRetro" framework as a new method for generating synthetic reasoning text. However, the four-step decomposition (product analysis → substructures → disconnection → synthons) is a direct computational instantiation of **Corey's Retrosynthetic Analysis (Corey, 1967; 1995)**. While the authors cite Corey, the manuscript frames the framework as a "data generation framework named SyntheticRetro" rather than an **LLM-automation of Corey's Logic**. Clarifying this heritage would better ground the work in the history of computer-aided synthesis design (CASD).

## 2. Novelty of Round-Trip RL
The primary methodological contribution is the transition from using **Round-Trip Accuracy** as a post-hoc filter (as established by **Schwaller et al., 2020**) to using it as an **online RL reward** via GRPO. This is a significant conceptual bridge that allows the model to optimize for chemical feasibility during training. However, the manuscript should more sharply differentiate this "active optimization" from the "passive filtering" used in prior transformer-based retrosynthesis.

## 3. The Forward Model Circularity Gap
A critical "hidden issue" in the RL stage is the risk of **Reward Hacking via Shared Bias**. If the forward synthesis model ($f_\phi$) and the policy model are trained on overlapping partitions of the same databases (e.g., ORDerly, USPTO), they may inherit the same systematic errors or data artifacts. In this regime, the policy can achieve high rewards by proposing reactant sets that the forward model *incorrectly* predicts as successful. A more rigorous evaluation would involve a "cross-dataset" round-trip check (e.g., using a forward model trained on different data) to confirm the robustness of the strategic reasoning.

## 4. Stereochemical and 3D Reasoning Omissions
Retrosynthetic "strategy" in drug discovery is fundamentally tied to **stereocontrol and 3D geometry**. By performing reasoning primarily on SMILES/SELFIES (1D abstractions) and focusing on "bond disconnections" without tracking chiral center inversions or enantiomeric purity, the framework remains chemically incomplete. Acknowledging this "stereochemistry gap" is essential for accurately mapping the framework's significance to real-world organic synthesis.

## Recommendation
- Reframe SyntheticRetro as an LLM-driven automation of Corey's retrosynthetic logic.
- Provide a "cross-verifier" ablation using a forward model trained on an independent dataset to mitigate circularity concerns.
- Address the limitations of 1D reasoning for stereochemically complex targets.
