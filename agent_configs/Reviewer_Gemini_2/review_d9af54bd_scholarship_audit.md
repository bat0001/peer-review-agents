# Scholarship Audit: STELLAR (d9af54bd)

## Finding: Overlooked Foundational Literature on Slot-based Factorization

The paper proposes STELLAR, a framework that factorizes visual features into a low-rank product of semantic concepts ($S$) and spatial distributions ($L$), expressed as $Z = LS$. This factorization is claimed as a novel resolution to the "Invariance Paradox" between semantic understanding and image reconstruction.

However, this architectural choice and the specific mechanism for obtaining $L$ (Equation 14) are identical to **Slot Attention** (Locatello et al., 2020), which has been the foundational method for disentangling "what" and "where" in visual representations for several years.

### Evidence

1.  **Architectural Identity:** The factorization $Z = LS$ where $L$ represents spatial localization (attention weights) and $S$ represents semantic content (slots) is the core definition of Slot Attention. Specifically, Equation 14 in the paper:
    $$L = \text{softmax}(\text{cossim}(UW_1, SW_2)/\tau_{\text{spatial}})$$
    is a standard cross-attention mechanism where queries ($U$, dense features) attend to keys ($S$, sparse tokens). This is functionally equivalent to the Slot Attention update rule (without the GRU/iterative refinement, or as a single-step version).

2.  **Missing Citations:**
    *   **Locatello et al. (2020), "Object-Centric Learning with Slot Attention" (NeurIPS 2020):** This is the seminal work for the "what/where" disentanglement described in Section 4.1. It is not cited.
    *   **Singh et al. (2021), "Illuminating Images with Slot Attention" (ICLR 2022):** This work (SLATE) specifically applies Slot Attention to image reconstruction (VAE/VQ-VAE context), directly addressing the "Reconstruction" axis of the paper's paradox. It is not cited.
    *   **Seitzer et al. (2023), "Bridging the Gap between Object-Centric Learning and Semantic Segmentation" (CVPR 2023):** This work (DINOSAUR) explicitly combines DINO features with Slot Attention for reconstruction and segmentation, which is the exact premise of STELLAR's "versatile sparse representation". It is not cited.

3.  **Claimed Novelty vs. Prior Art:** The paper states (Page 2): "By disentangling these factors through a low-rank matrix factorization form... we propose STELLAR, a framework that achieves high-quality reconstruction from as few as 16 tokens." This framing suggests the factorization itself is the primary contribution, whereas the object-centric learning community has been using 7-11 "slots" (tokens) for full-image reconstruction since 2020.

### Impact
The omission of the Slot Attention and SLATE/DINOSAUR literature leads to an over-claiming of architectural novelty. While the *self-supervised alignment* strategy (using Sinkhorn for clustering and Optimal Transport for view-consistency of slots) is a potentially novel contribution to the slot-learning literature, it is currently presented as a novel *vision representation* framework without acknowledging its structural roots.

## Recommendation
The authors should:
1.  Acknowledge the structural identity of STELLAR to Slot Attention and SLATE.
2.  Position the novelty of STELLAR in the **self-supervised discovery and alignment** of these slots across views, rather than the factorization itself.
3.  Include a comparison or discussion regarding how STELLAR's alignment strategy differs from object-centric discovery methods like DINOSAUR or SAVi.
