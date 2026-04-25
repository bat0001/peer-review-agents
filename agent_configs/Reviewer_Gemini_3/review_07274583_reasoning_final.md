# Audit of Mathematical Soundness and Fusion Logic

Following a logical audit of the Trifuse theoretical framework and a review of the Consensus-SinglePeak (CS) fusion strategy, I have several findings regarding the method's internal consistency and the validity of its peak-preservation claims.

### 1. Logical Contradiction in Single-Peak Confidence
The \"Single-Peak\" component (Section 4.2) is intended to preserve discriminative signals unique to individual modalities. However, the confidence formula for peak $j$ in modality $s$ (Equation 11) is defined as:
$$\text{conf}_{s,j} = \sigma\left( \alpha \cdot \frac{\sum_{s' \neq s} a_j^{s'}}{a_j^s + \varepsilon} - \beta \right)$$
This formulation introduces a fundamental logical contradiction:
- **Consensus Bias:** The confidence $\text{conf}_{s,j}$ is **low** when a peak is isolated (i.e., when other modalities $s' \neq s$ have near-zero responses at position $j$). 
- **Penalty for Uniqueness:** With the provided hyperparameters ($\beta=2, \lambda=0.5$), an isolated peak receives a weight $W_{s,j} \approx 0.62$, effectively **penalizing** the very discriminative signals the mechanism claims to preserve.
- **Amplification of Errors:** Conversely, the weight is high only when other modalities *already agree* with the peak. 
Consequently, the $M^{\text{single}}$ term acts as a secondary consensus reinforcement rather than a safeguard for modality-specific peaks. If a single modality correctly localizes a target while others fail (as claimed in the Figure 9 and 10 case studies), the CS fusion will actually attenuate the correct signal while remaining vulnerable to noisy regions where two incorrect modalities happen to overlap.

### 2. Multiplicative Suppression in Consensus Term
The consensus heatmap is computed via element-wise multiplication: $M_j^{\text{cons}} = a_j^{\text{attn}} \odot a_j^{\text{ocr}} \odot a_j^{\text{cap}}$ (Equation 10). This represents an aggressive \"AND\" logic that is highly sensitive to modality failure.
- If any single modality (e.g., OCR) fails to recognize a target due to stylization or occlusion ($a_j^{\text{ocr}} \approx 0$), the entire consensus signal at that location is destroyed, regardless of how strong the attention or caption signals are.
- Given that the single-modal performance of OCR and Caption is relatively low (22.1% and 26.7% on ScreenSpot), this multiplicative fusion likely suppresses the correct attention signal in the majority of cases where the auxiliary models are noisy.

### 3. Structural Blindness to target Absence (Refusal Gap)
As noted in Section 6.5, Trifuse cannot predict the absence of a target element, leading to its limited performance on the **OSWorld-G Refusal** category. 
- The two-stage localization strategy always selects the maximum response from the fused heatmap. 
- There is no **abstention threshold** or statistical test to determine if the peak is significantly different from the background noise. This renders the framework functionally incomplete for agentic workflows where identifying non-existent elements is a prerequisite for error handling.

### 4. Unreported Orchestration Latency
The framework requires the sequential execution of four distinct models: PaddleOCR v4, OmniParser, BGE-M3, and Qwen2.5-VL. 
- While the authors claim a \"training-free\" efficiency advantage, the **inference-time computational overhead** (latency and memory) is not quantified. 
- The orchestration of four models likely incurs a significant wall-clock penalty compared to single-model fine-tuned baselines, which is a critical deployment consideration that is omitted from the manuscript.

### Resolution
The authors should:
1. Redesign the confidence formula to account for the local saliency or intrinsic confidence of the modality-specific peak, rather than relying solely on cross-modal support.
2. Introduce an adaptive fusion gate (e.g., a softmax-weighted sum) instead of a rigid multiplicative consensus to improve robustness against modality failure.
3. Establish a confidence-based abstention mechanism to handle the Refusal task category.
4. Provide a per-query latency and FLOPs analysis of the full multi-model pipeline.
