# Scholarship & Logic Audit: Paper 07274583 (Trifuse)

## 1. Design-Math Mismatch (The Single-Peak Contradiction)
A fundamental structural contradiction exists between the stated goal of the \"Single-Peak\" mechanism and its mathematical implementation in Equation 11.

- **Design Goal:** The manuscript states that the Single-Peak term is intended to \"preserve strong and discriminative responses **unique** to individual modalities\" (Section 4.1) which might be absent in others.
- **Implementation (Eq. 11):** The confidence score $\text{conf}_{s,j}$ is defined as a sigmoid of the ratio $(\sum_{s' \neq s} a_j^{s'}) / (a_j^s + \varepsilon)$. 
- **The Contradiction:** This formula identifies confidence by measuring **agreement** from other modalities. For a peak that is truly unique to modality $s$, the responses $a_j^{s'}$ for $s' \neq s$ are near-zero, resulting in a **minimal confidence score** and subsequent **down-weighting** ($W_{s,j} < 1$).
- **Impact:** Both the \"Consensus\" term (multiplicative AND logic) and the \"Single-Peak\" term (agreement-weighted) require cross-modal support. The framework possesses no mechanism to actually protect unique, modality-specific peaks, rendering the design rationale for the two-term fusion strategy logically self-defeating.

## 2. The White-Box Access Barrier
Trifuse's reliance on extracting internal attention maps from the MLLM backbone creates a significant deployment barrier:
- The framework is **inapplicable to closed-source frontier models** (e.g., GPT-4o, Claude 3.5, Gemini 1.5 Pro) where internal activations are not exposed via API.
- Since coordinate-based grounding from black-box models is the current industry standard, the omission of comparisons against these frontier alternatives limits the scholarship. It remains unclear if Trifuse's complex white-box pipeline offers any advantage over a standard black-box coordinate prediction from a stronger model.

## 3. Unquantified Orchestration Latency
The proposed pipeline requires the sequential execution of four distinct models: PaddleOCR, OmniParser, BGE-M3, and Qwen2.5-VL. 
- The manuscript lacks a wall-clock or computational cost analysis for this multi-stage orchestration. 
- A single fine-tuned model (the baseline Trifuse seeks to avoid) may be significantly faster and more resource-efficient than running this sequential quartet, yet this trade-off is not quantified.

## 4. Missing Baseline: SE-GUI (NeurIPS 2025)
The paper omits comparison with **SE-GUI (NeurIPS 2025)**, an attention-based grounding model that uses minimal RL (3,000 samples) to achieve state-of-the-art results on ScreenSpot-Pro. Including this baseline is necessary to quantify the performance gap between \"training-free\" and \"minimal-training\" paradigms.

**Final Recommendation:** **Weak Reject**. The core fusion logic is mathematically contradictory to its design goals, and the white-box constraint limits its practical relevance compared to existing black-box alternatives.
