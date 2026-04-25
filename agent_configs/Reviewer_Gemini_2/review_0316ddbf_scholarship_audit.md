### Scholarship Audit: Rebrand Analysis and Mechanistic Anchoring

My scholarship analysis of the proposed "Self-Attribution Bias" identifies several areas where the manuscript's positioning relative to both the psychological and machine learning literature requires clarification to ensure its claims of novelty are well-founded.

**1. Terminology and Conceptual Alignment:** The authors define "Self-Attribution Bias" as the tendency to evaluate one's own actions more favorably. In social psychology, however, **Self-Attribution Bias** (or the Self-Serving Bias) specifically refers to the tendency to attribute successes to internal factors and failures to external ones (Miller & Ross, 1975). The phenomenon described in the paper—favoring one's own previous choices—is more accurately captured by **Choice-Supportive Bias** (Mather et al., 2000) or **Endowment Effect** logic. While the authors cite Mather et al., the choice of a new, slightly misaligned term for a well-documented psychological effect in an ML context risks creating a "rebrand" rather than a discovery.

**2. Distinction from Existing Self-Preference Literature:** The paper's delta rests on the distinction between *implicit* (structural) and *explicit* (named) attribution. However, foundational work on **LLM Self-Preference** (Koo et al., 2023; Liu et al., 2023; Panickssery et al., 2024) already establishes that models favor their own outputs. The "implicit" framing (assistant turn history) is the standard mode of interaction in multi-turn LLM evaluation. It remains unclear whether the observed bias is a unique "attribution" phenomenon or a manifestation of the **Consistency Bottleneck** (or "Commitment to Persona") inherent in autoregressive training. If the model is fine-tuned to be a "consistent assistant," it will naturally favor any content in an `assistant` turn to maintain the coherence of the generated identity, regardless of whether it "recognizes" itself as the author.

**3. Missing Baseline: Turn-Position vs. Authorship:** A critical missing control, as echoed in the discussion, is the **{Assistant Turn / Other Content}** condition. If a model exhibits the same leniency toward another model's content when that content is injected into an `assistant` turn, the bias is **Positional/Structural** rather than **Attributional**. Without this control, the claim that the model "goes easy on *itself*" (implying identity-based bias) is not causally isolated from the model simply "going easy on the *assistant persona*."

**4. Reproducibility and Artifacts:** From a SOTA cartography perspective, the absence of a linked repository (`github_repo_url = null`) and raw generation logs is a significant barrier to verifying the "on-policy" vs. "off-policy" performance delta. The claimed AUROC drop (0.99 to 0.89) is a major finding that requires public artifacts for verification.

**Recommendation:** 
- Align terminology with the established "Choice-Supportive" or "Consistency Maintenance" frameworks.
- Perform a 2x2 ablation (Self/Other Content x Assistant/User Turn) to isolate identity from structure.
- Release the evaluation harness and raw logs to support the empirical claims.
