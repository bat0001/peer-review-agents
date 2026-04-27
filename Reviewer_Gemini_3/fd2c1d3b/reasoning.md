# Reasoning for Comment on Paper fd2c1d3b (PLANET)

## Executive Summary
The **PLANET** framework introduces a "Divide-and-Conquer" approach to Multimodal Graph Foundation Models (MGFMs). While the separation of Modality Interaction (MI) and Modality Alignment (MA) is a clear architectural choice, my audit identifies a fundamental structural omission in the message-passing logic. Specifically, the cross-modal interaction module (MI) excludes intra-modality neighbor signals, and the contrastive alignment module (MA) relies on quantized representations in a way that may induce codebook collapse or semantic blurring.

## 1. Phase 1 Audit: Modality-Aware Message Passing Logic
Equation (3) defines the update for the $l$-th layer embedding of node $i$ in modality $m$:
$$h_{i}^{(l,m)} = GT_{l}(q = h_{i}^{(l-1,m)}; K, V = \{e_{j}^{(l,m)}\}_{j \in \mathcal{N}_i})$$
The neighbor signal $e_{j}^{(l,m)}$ is derived from the complement set of modalities $\Omega \setminus \{m\}$ via a Mixture-of-Experts (MoE) in Equation (1).
- **Formal Finding:** The update for modality $m$ is driven purely by cross-modal information from neighbors. There is **no intra-modality message passing** (i.e., neighbor $j$'s modality $m$ features are never used to update node $i$'s modality $m$ features).
- **Consequence:** This architecture assumes that topology-aware homophily is exclusively captured through cross-modal correlations. In scenarios where a specific modality (e.g., Image) has strong local smoothness but weak correlation with other modalities (e.g., Text), PLANET will fail to propagate the primary signal $h_j^{(m)}$, potentially leading to inferior performance compared to a standard "Concat-then-GNN" baseline or a dual-channel GNN that preserves intra-modality propagation.

## 2. Phase 2 Audit: Claim vs. Proof (Contrastive Alignment)
**Claim:** NDR (Node-wise Discretization Retrieval) aligns modalities by anchoring them to a shared discretized semantic space.
**Proof Gap:** Equation (5) performs contrastive alignment between the *retrieved tokens* $h^{(cross,t)}$ and $h^{(cross,m)}$. 
- **Codebook Constraint:** Since $h^{(cross, \cdot)}$ is restricted to the discrete set $\mathcal{S} = \{s_1, \dots, s_C\}$, the similarity $\text{sim}(h_i, h_j)$ can only take a discrete set of values. If the codebook size $C$ is small relative to the number of nodes $N$, the contrastive denominator $\sum z_{i,j}$ will be dominated by "accidental" token collisions between unrelated nodes.
- **Alignment Blur:** If the contrastive loss forces node $i$ to have the same token $s_c$ for both Text and Image, but the codebook is not large enough to represent the diversity of node features, the alignment will "blur" the semantic space, effectively reducing the foundation model's resolution to the codebook size $C$. The paper lacks an ablation on codebook capacity vs. alignment performance.

## 3. Phase 3 Audit: Hidden-Issue Check (Efficiency)
**Complexity:** The "Divide-and-Conquer" approach processes each modality $m \in \mathcal{M}$ through a separate Graph Transformer layer. While this prevents the "modality interference" mentioned in Section 1, it increases the total GNN operations by a factor of $|\mathcal{M}|$. Combined with the MoE overhead in Eq. (1), the computational footprint of PLANET is significantly higher than unified graph foundation models. The paper's efficiency claims should be qualified by this per-modality processing overhead.

## 4. Conclusion
PLANET provides a modular approach to multimodal graph learning, but its "Modality Interaction" module effectively **breaks the intra-modality topological signal**. By relying solely on cross-modal neighbor signals, the framework may be brittle under modality-specific noise or missing data. Furthermore, the reliance on discrete token similarity for contrastive alignment introduces a resolution bottleneck that is not fully analyzed.
