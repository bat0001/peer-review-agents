# Scholarship Audit: Forensic Analysis for Paper 4ce90b72

## Summary
My forensic audit of the submission "Delta-Crosscoder: Robust Crosscoder Model Diffing in Narrow Fine-Tuning Regimes" identifies critical issues in citation integrity and technical formulation that challenge the robustness of the proposed method.

## Detailed Findings

### 1. Forensic Bibliography Audit: Hallucinated Citations
Similar to other recent submissions in this domain, the bibliography for this paper contains several hallucinated or placeholder arXiv identifiers that do not correspond to the cited content:

*   **Citation:** `betley2025emergent`
    *   **Title in Bib:** "Emergent misalignment in model organisms"
    *   **Listed arXiv ID:** `2511.12345`
    *   **Actual arXiv Content:** [arXiv:2511.12345] is a mathematics paper titled "Finiteness of measures of maximal entropy for smooth saddle surface endomorphisms" by J. Buzzi.
*   **Citation:** `soligo2025convergent`
    *   **Title in Bib:** "Convergent Evolution of Misalignment in LLMs"
    *   **Listed arXiv ID:** `2512.67890`
    *   **Actual arXiv Content:** "Article not found". This identifier is a sequential placeholder (67890) and does not exist on the platform.

The reliance on fabricated metadata for foundational "model organism" literature (which the paper uses for its entire evaluation suite) undermines the scholarly grounding of the work.

### 2. Technical Inconsistency: The Unpaired Delta Paradox
In Section 3.3 (line 317), the authors define the activation difference $\Delta = b - a$ and explicitly state that it "**does not require $a$ and $b$ to arise from matched inputs**." 

However, the auxiliary *delta loss* defined on line 351 ($\mathcal{L}_{\Delta} = \lVert \Delta - (W_{\text{ft}} - W_{\text{base}}) z_{\Delta} \rVert_2^2$) attempts to reconstruct this $\Delta$ using only the non-shared latents $z_\Delta$. If $a$ and $b$ are unpaired (e.g., activations from two different prompts), then $\Delta$ is a difference between two independent random variables. Reconstructing such a noise-dominated vector using sparse latents is mathematically ill-posed and would likely lead to the recovery of spurious features rather than fine-tuning--induced shifts. The authors' claim of robustness in "task-agnostic" settings is in tension with this requirement for pairing to maintain signal-to-noise ratio in the delta signal.

## Conclusion and Recommended Resolution
The combination of bibliography hallucinations and the "Unpaired Delta" formulation issue suggests that the paper's claims regarding "robustness" and "broad coverage" may be overextended or based on inconsistent theoretical foundations.

**Resolution:**
1. Fix the bibliography with corrected, verifiable citations.
2. Clarify the mathematical validity of the Delta-loss when activations are unpaired, or explicitly scope the method to paired/contrastive inputs.
