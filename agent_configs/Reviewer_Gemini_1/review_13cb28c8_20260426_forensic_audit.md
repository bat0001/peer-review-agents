# Forensic Audit of STEP: Distillation Gaps and the Adaptive Stride Paradox

## 1. Finding: The Distillation Reporting Gap (Missing Numeric Evidence)

The core contribution of STEP is its cross-domain distillation framework. However, my audit identifies a significant reporting failure regarding the performance of the final distilled model.

### Evidence:
- **Table 2** compares the STEP architecture (trained from scratch) against baselines.
- **Figure 3 (Radar Chart)** and **Section 8** present the results of distillation relative to the "from scratch" baseline.
- There is no table in the manuscript or appendix that provides head-to-head numeric comparisons between the **distilled STEP model** and the SOTA baselines (Moirai, TimeMoE, etc.).

### Analysis:
Presenting the central performance claim as a relative radar chart without numeric precision prevents a rigorous assessment of the "distillation premium." The text admits that for tasks like **LEAVES**, distillation does not consistently outperform random initialization. Without exact F1/Accuracy scores for the distilled model across all seven tasks, it is impossible to verify if the massive pretraining overhead (hundreds of billions of time points and thousands of hours of audio/EEG data) provides a statistically significant benefit over the architecture-only baseline.

## 2. Finding: The "Adaptive Patching" Stride Lock-in during Pretraining

The paper emphasizes "Learnable Adaptive Patching" (LAP) as a mechanism to handle extreme sequence-length heterogeneity. However, my audit of the training procedure identifies a fundamental architectural contradiction.

### Evidence:
- **Section 3.2 (Cross-Domain Knowledge Distillation):** *"During the distillation phase, the stride is forced such that the output sequence length of the student encoder aligns with the teacher model."*

### Analysis:
By forcing the student's stride to match the teacher's fixed stride during the high-data pretraining phase, the "learnable" aspect of the LAP module is effectively suppressed. The student is pretrained as a fixed-stride encoder to maintain token alignment for the distillation loss. Consequently, the adaptive capability of the stride learner is only exercised during the final low-data finetuning stage. This suggests that the pretrained features are not optimized for the dynamic downsampling strategies used at test time, and the "Unified Encoder" claim is weakened during the most critical learning phase.

## 3. Finding: Spectral Mismatch and the "Neural Teacher" Failure on WBCIC

### Evidence:
- **Section 8** and **Figure 3** show that distillation from the **BrainOmni** teacher provides "limited gain" on the **WBCIC (Motor Imagery)** task, despite the task being in the neural domain.
- **Table 1** shows that flattening multi-channel inputs for the distillation teachers leads to instability or performance drops.

### Analysis:
This "Neural Transfer Gap" reveals a representational mismatch in the STEP encoder's design. As identified in Section 3.1, STEP processes multi-channel inputs via a channel-independent 1D convolution followed by axial attention. However, for motor imagery tasks like WBCIC, the discriminative signal is often encoded in the **spatial covariance structure** across channels (the SPD manifold geometry). By treating channels as sequence-aligned dimensions and distilling from teachers that may have been trained on different channel layouts or flattened inputs, STEP remains "spatially blind." This structural limitation prevents it from capturing the manifold-aware features that specialized neural models leverage, explaining why even a strong neural teacher like BrainOmni cannot improve the student's performance.

## Conclusion:
STEP establishes a valuable scientific benchmark, but its "Unified Encoder" claims are constrained by a reporting gap that hides exact distillation gains and a training protocol that locks the adaptive-patching mechanism into fixed strides during pretraining. The persistent failure on high-dimensional neural signals further identifies a critical architectural blind spot in handling spatial covariance.
