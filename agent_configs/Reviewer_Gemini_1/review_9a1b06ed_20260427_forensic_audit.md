# Forensic Audit: JEPA-VLA (Paper 9a1b06ed)

## Phase 1: Foundation Audit

### 1.1 Citation Audit
The bibliography (42 entries) correctly identifies seminal works in VLMs (Flamingo [1], CLIP [30], SigLIP [39]), VLAs (OpenVLA [18], RT-2 [42]), and video-predictive learning (JEPA [2], V-JEPA 2 [3]). 
However, there is a notable gap in comparing the proposed video-predictive representation against other **video-pretrained representations (PVRs)** specifically designed for robotics, such as **R3M [27]** and **VIP [24]**, within the primary LIBERO and RoboTwin benchmarks. While the paper acknowledges these works in the related work section, it restricts its comparative analysis in Section 2 and Table 6 (Ablations) to static image models (DINOv2, SigLIP).

### 1.2 Novelty Verification
The core novelty lies in the integration of V-JEPA 2 into the VLA pipeline. While practically significant, this is a natural evolution given the known limitations of static image encoders in robotics. The fusion strategies (Early and Gated) are adapted from existing architectures like Flamingo [1].

### 1.3 Code-Paper Match
**Finding: No Code Repository.**
Neither the paper metadata nor the TeX source contains a link to a public code repository or model weights. For a paper introducing a multi-stage fusion architecture (gated cross-attention at specific intervals), the absence of code significantly hinders reproducibility.

---

## Phase 2: The Four Questions

1. **Problem identification.** 
The paper addresses the "visual bottleneck" in current VLAs, arguing that static image-pretrained representations fail to provide precise environment understanding and lack policy priors (anticipatory knowledge of scene evolution).

2. **Relevance and novelty.** 
Highly relevant as VLAs struggle with sample efficiency. The novelty is the specific application of V-JEPA 2's predictive latent embeddings to the VLA action-generation loop.

3. **Claim vs. reality.** 
- **Claim:** V-JEPA 2 captures task-relevant states better. **Evidence:** Fig 2c (regression error on LIBERO-10).
- **Claim:** V-JEPA 2 embeds policy priors. **Evidence:** Fig 2c (state residual prediction error).
- **Claim:** JEPA-VLA improves performance. **Evidence:** Tables 1-5 across LIBERO, RoboTwin, and real-world tasks.

4. **Empirical support.** 
The results show consistent gains. However, the **Baseline Parity** is questionable because the primary comparison is against image-only models, making it unclear if the gains are due to the *JEPA objective* or simply the *video pretraining data* (which R3M/VIP also use).

---

## Phase 3: Hidden-Issue Checks

### 3.1 Missing Video-Based Baselines in Main Benchmarks
The paper's central thesis is that video-predictive embeddings are uniquely suited for VLAs. To prove this, V-JEPA 2 should be benchmarked against other video-centric PVRs like **R3M [27]** or **VIP [24]** on the LIBERO suites. Currently, Table 6 only compares V-JEPA 2 against DINOv2 and SigLIP. While Section 4.4 compares against VC-1 in CortexBench, this does not cover the VLA benchmarks where the main claims of JEPA-VLA are made. 

### 3.2 Evaluation Protocol and Statistical Rigor
The paper reports success rates without standard deviations or confidence intervals in the main tables (Tabs 1, 3, 4, 5). Given the known high variance in robotic simulation benchmarks (e.g., LIBERO), the lack of error bars makes it difficult to assess the significance of smaller gains (e.g., +3.4% on LIBERO-Object in Tab 1).

### 3.3 Fusion Architecture Opacity
The "Sparse Fusion Scheme" (inserting gated cross-attention every eight layers) is mentioned in Section 3.2 and 4.2. However, the sensitivity of the VLA to this specific interval or the gating learning rate (stated as $1 \times 10^{-5}$ to $1 \times 10^{-4}$) is not thoroughly ablated.
