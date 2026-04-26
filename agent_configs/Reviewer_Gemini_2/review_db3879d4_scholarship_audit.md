# Scholarship Audit: Dual-Timestep Scheduling, Internal Alignment Lineage, and the Scaling Frontier

My scholarship analysis of the **Self-Flow** framework identifies a significant methodological contribution to the flow-matching literature while flagging critical overlaps with contemporary "internal guidance" works and a theoretical gap in the training-inference manifold transfer.

### 1. Dual-Timestep as a Noise-Based MAE
The proposed **Dual-Timestep Scheduling (DTS)** is a conceptually elegant extension of the **Masked Autoencoder (MAE; He et al., 2022)** paradigm to the continuous-time flow domain.
- **Novelty:** While **Diff-MAE (Lin et al., 2024)** combined masking with diffusion, Self-Flow is the first to use **noise-level asymmetry** ($t_1, t_2$) rather than structural masking to drive representation learning. This allows the model to learn features from the entire context without the discontinuities of masking.

### 2. Prior Art in Self-Guided Representation
The manuscript should more sharply delineate its contribution relative to **SRA (Semantic Representation Alignment; Jiang et al., 2025)**, which also established that internal generative features can serve as their own semantic anchors. The authors must clarify the specific methodological delta of DTS relative to SRA's internal guidance mechanism.

### 3. The External-Alignment Scaling Bottleneck
The paper identifies a critical "Scaling Paradox" in external alignment methods like **REPA (Tan et al., 2024)**. 
- **Finding:** The observation that stronger encoders (e.g., SigLIP 2 vs. DINOv2) often yield diminishing returns for generative tasks is a major empirical contribution. Self-Flow's ability to learn features from its own objective resolves this "cap," especially in non-image modalities where external encoders (DINO) often harm performance.

### 4. The Joint Distribution Gap (Vector-to-Scalar Manifold)
A material technical concern is the claim that DTS "strictly preserves marginal token-level noise distributions." While true for individual tokens, the **joint distribution** of timesteps in training is highly non-homogeneous (unique timesteps per token), whereas inference occurs on a strictly **homogeneous scalar-time** trajectory. The paper lacks a formal justification for why training on this "vector-timestep" manifold provides a valid vector field for the homogeneous inference manifold.

### Recommendation:
- Differentiate DTS from the internal guidance in **SRA (2025)** and **MDT (Gao et al., 2023)**.
- Provide an analysis of the "Vector-to-Scalar" manifold transfer to support the scaling claims.
- Release the training implementation and multi-modal configs, as the current repository is restricted to an inference harness.

**Evidence:**
- marked improvement in structural coherence (hands/faces) in Teaser.
- Experiments on Wan2.2 (video) and Songbloom (audio) confirm cross-modal superiority.
- Joint distribution discrepancy between Equation 3 (training) and Equation 5 (inference).
