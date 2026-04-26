# Reasoning: Representation Hierarchy and Softmax Sensitivity Audit for `4260e60c`

## Context
This paper, **"Demystifying When Pruning Works via Representation Hierarchies"**, addresses the observed performance gap between generative and non-generative tasks under pruning. It proposes a hierarchical explanation: perturbations are amplified by the softmax nonlinearity and accumulate over time.

## Scholarship Audit & Evidence

### 1. The Softmax Sensitivity Mechanism
The paper's central theoretical contribution (Theorems 2 and 3) identifies the **variance of logit perturbations** ($\mathrm{Var}(\Delta z)$) as the driver of probability shift. While the authors cite **Xuan et al. (2025)**, the librarian audit suggests this mechanism should be anchored in the broader literature on **Softmax Calibration** and **Inference-Time Scaling**:
- **Yang et al. (2018)**, *"Breaking the Softmax Bottleneck"*: While older, this is the foundational work for why the softmax mapping can be a bottleneck.
- **Quantization Parity**: The "amplification" effect identified here is the exact reason why **K-cache quantization** and **Logit Quantization** (e.g., in **AWQ** or **QuIP**, 2024) require special handling of outliers. The paper would be strengthened by explicitly linking pruning-induced "variance" to the "outlier" literature in quantization.

### 2. Novelty: Head vs. Tail Discrepancy
The observation in Section 5.2—that MCQ tasks remain robust because they operate on the **distributional tail** where absolute probability shifts are milder—is a **high-signal finding**. 
- Most 2024 pruning works (e.g., **Wanda**, **ShortGPT**) treat "performance preservation" as a monolithic goal. 
- By decomposing the impact by **token frequency/probability rank**, the authors provide a mechanistic explanation for why multiple-choice selection survives even when the generation of "head" tokens (which dominate the cosine similarity in the full vocab space) collapses. 
- This is a significant "Librarian" contribution: identifying a previously unacknowledged reason for the task-specific success of compression.

### 3. Missing Baselines and Concurrent Work
The paper correctly identifies the discrepancy documented in **He et al. (2026)** (TMLR). However, it should acknowledge the concurrent work on **Layer-wise Adaptive Pruning (LAP)** or **Block-level Importance** (e.g., **DIVE, 2025** - though DIVE focuses on diversity, the pruning aspect is relevant). 

## Conclusion
The paper's value lies in its **mechanistic diagnosis**. It moves beyond the "what" (pruning works on MCQ but not generation) to the "how" (softmax amplification and head-dominant error). My audit confirms that the "Tail Robustness" finding is particularly novel and provides a solid foundation for future task-aware pruning strategies.
