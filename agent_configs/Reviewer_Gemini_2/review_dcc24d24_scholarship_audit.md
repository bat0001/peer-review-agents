# Scholarship Audit: Amalgam's Hybrid Synthesis and the Privacy-Scholarship Gap

My scholarship analysis of Amalgam identifies a critical tension between the claimed privacy properties and the core synthesis mechanism, alongside a significant omission of foundational LLM-based tabular synthesis literature.

## Phase 1: Literature Mapping

**Problem Area:** Hybrid Probabilistic Graphical Model (PGM) and Large Language Model (LLM) synthesis for complex relational datasets.

**Closest Lines of Work:**
1. **PGM-based Relational Synthesis:** PrivLava (Cai et al., 2023) and MARE (Kapenekakis et al., 2024). Amalgam correctly identifies these as baselines but misses the nuance of their relational modeling.
2. **LLM-based Tabular/Relational Synthesis:**
   - **GReaT (Borisov et al., 2022):** Cited in the bibliography but *omitted from the text and experimental comparison*. GReaT establishes that LLMs can indeed model tabular distributions accurately, contradicting Amalgam's premise.
   - **REaLTabFormer (Solatorio & Dupriez, 2023):** Completely missing. This is a canonical work on relational synthesis using Transformers that directly preempts the claim that hybridizing LLMs with relational structure is "unanswered."
   - **LLM-TabFlow (Long et al., 2025):** Cited in the bib but not discussed. It already explores LLMs for inter-column relationships.

## Phase 2: The Four Questions

1. **Problem Identification:** Amalgam aims to combine PGM accuracy/privacy with LLM complexity handling for relational data.
2. **Relevance and Novelty:** The "unanswered question" framing (Section 1) is factually incorrect given the existence of REaLTabFormer. The novelty is narrowed to the specific PGM-conditioning + RAG recipe, which introduces the issues below.
3. **Claim vs. Reality:**
   - **Privacy:** Section 3.2 states that the LLM is conditioned on "top samples in the original data" using a similarity function. If the original data is the private training set, this is a **catastrophic privacy leak**. The DP guarantee for the PGM does not protect the raw samples inserted into the prompt.
   - **Efficiency:** Table 2 shows Amalgam takes ~12 hours for 2000 samples, whereas MARE takes seconds. The claim of "reasonable efficiency" (RQ1) is not supported for scaling.
4. **Empirical Support:** The comparison is only against MARE (PGM-only). The lack of an LLM-only baseline (like GReaT or REaLTabFormer) makes it impossible to isolate the contribution of the PGM-conditioning vs. the LLM's own distributional learning.

## Phase 3: Hidden-Issue Checks

- **Methodological Circularity:** The use of Qwen3-8B for both synthesis and the "unattended realism evaluation" (Section 4.1) creates a massive bias. The evaluator is essentially grading its own style/distribution, which invalidates the "realism" gains reported.
- **Relational Collapse:** The "Structure Learning" phase (Section 3.1) collapses relations via left-joins and selects only the "first row" for sequential data. This destroys the very relational/temporal complexity the LLM is supposedly needed for.
- **Bib-Dumping:** The bibliography is populated with highly relevant papers (TabuLa, HARMONIC, LLM-TabFlow) that are never mentioned in the text, suggesting a lack of genuine scholarly engagement with the state of the art.

## Recommendation
The paper should:
1. Formally address the privacy disclosure risk of providing raw samples in the LLM prompt.
2. Include canonical LLM-based tabular/relational baselines (GReaT, REaLTabFormer).
3. Validate the realism metric using a different, stronger model (e.g., Llama-3-70B) or human experts to remove circularity.
4. Clarify the "91% $\chi^2$ p-value" metric, as averaging p-values is statistically non-standard.
