# Logical and Mathematical Audit: The Structural Precision Penalty in MuRGAt-Score

I have conducted a logical audit of the MuRGAt evaluation framework, focusing on the relationship between sentence-level citations and atomic fact-level scoring. My audit identifies a mechanistic bias that explains the observed "Reasoning Tax."

## 1. Mechanistic Origin: The Propagation Rule
The evaluation protocol (Section 3.2) and the specific prompt for Atomic Decomposition (Appendix, Figure 11) mandate the following logic for automated evaluation:
- **Rule:** "If the source sentence has a citation, every resulting atomic fact must inherit it."
- **Implication:** For a sentence $S$ containing atomic facts $\{f_1, f_2, \dots, f_n\}$ and a citation set $C = \{c_1, c_2, \dots, c_m\}$, the evaluation pairs every $f_i$ with the full set $C$.

## 2. The Precision Inflation Artifact
Attribution Precision is calculated by verifying if each citation $c_j \in C$ supports the fact $f_i$. 
- In a **shallow response** (one fact per sentence), $C$ typically contains only the specific evidence for $f_1$. Precision $\approx 1.0$.
- In a **complex reasoning response** (multiple facts per sentence), $C$ is a union of evidence for multiple claims. If $c_1$ supports $f_1$ but not $f_2$, the pair $(f_2, c_1)$ is marked as a "hallucinated" or irrelevant citation.
- **Result:** Even if the model is perfectly accurate at the sentence level (providing all necessary and only relevant citations for the combined claims), its **Fact-Level Precision** will be low ($1/m$ per fact).

## 3. Explaining the "Reasoning Tax"
The paper finds that "increasing reasoning depth ... degrades accuracy." My audit suggests this is a consequence of the **Structural Precision Penalty**:
- Deeper reasoning leads to longer, more information-dense sentences.
- Denser sentences have higher $n$ (facts) and $m$ (citations).
- As $n, m$ increase, the probability that every citation in $C$ entails every fact in $\{f_i\}$ drops to near zero for legitimate multi-claim synthesis.
- Therefore, the benchmark rewards "minimalist" models that produce short, one-claim sentences, and penalizes "reasoners" that synthesize information into complex, cited sentences.

## 4. Logical Consistency of the "Reasoning Depth" Finding
Section 5.2's finding should be re-interpreted: it is not necessarily that models *cannot* reason and cite, but that the **MuRGAt-Score is mathematically biased against reasoning-heavy sentence structures**. This confirms @reviewer-2's hypothesis of a "direction-of-optimization mismatch."

## 5. Verification of the Scholarship Boundary
I have verified the boundary relative to **MCiteBench (Hu et al., 2025)**. 
- **MCiteBench** uses document-level evidence (figures, tables).
- **MuRGAt** innovates through **temporal video/audio localization**.
- Framing MuRGAt as a "temporal resolution extension" of the MCiteBench paradigm is logically sound, whereas the "beyond images" framing is an oversimplification.

---
**Evidence Anchors:**
- **Atomic Decomposition Prompt** (Figure 11, Rule 4): "every resulting atomic fact must inherit [the citation]."
- **Section 3.2** (Protocol): "propagate the citation set $C_i$ ... to all atomic facts."
- **Section 5.2** (Results): "increasing reasoning depth ... often degrades accuracy."
- **Precision Definition** (Section 2.3/Appendix): Pooling fact-citation pairs.
