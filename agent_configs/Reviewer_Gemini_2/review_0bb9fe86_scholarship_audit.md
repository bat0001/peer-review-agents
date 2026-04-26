# Reasoning and Evidence for Review of "Simple Baselines are Competitive with Code Evolution" (0bb9fe86)

## Literature Mapping

### Problem Area
Systematic evaluation of code evolution methods (LLMs evolving/mutating code) against simple baselines (IID Sampling and Sequential Conditioned Sampling).

### Prior Work Mapping
- **Scientific Discovery:** Direct comparison (Novikov et al., 2025 - AlphaEvolve).
- **Agentic Scaffolds:** Direct comparison (Hu et al., 2024 - ADAS).
- **ML Competitions:** Direct comparison (Chan et al., 2024 - MLE-bench; Jiang et al., 2025 - AIDE).
- **SOTA Methods:** Related work (Lange et al., 2025 - ShinkaEvolve).

## Citation Audit
- `novikov2025alphaevolve`: Real paper (2025).
- `hu2024automated`: Real paper (2024).
- `jiang2025aide`: Real paper (2025).
- `lange2025shinkaevolve`: Real paper (2025).
- `chan2024mle`: Real paper (2024).
- All citations are legitimate and correctly placed within the 2024–2026 timeline.

## Analysis of Claims

### 1. The "Search Space vs. Pipeline" Trade-off
**Finding:** The paper demonstrates that changing a problem's formulation (search space) or prompt domain knowledge has a much larger impact on performance than the search algorithm itself.
**Evidence:** Section 5.1 shows that all methods (baselines and ShinkaEvolve) found an improved bound of 0.3482 for the uncertainty inequality when the formulation was improved, whereas the gain from search-pipeline optimization within the old formulation was much smaller (0.3523 to 0.3521).
**Impact:** This is a vital scholarship finding that challenges the current research emphasis on complex evolutionary operators, suggesting that domain-specific verifier design is the true performance ceiling.

### 2. The "Fitness-Blind" Selection in SCS
**Observation:** The Sequential Conditioned Sampling (SCS) baseline picks a **random subset** of successful programs for the next generation, rather than the **fittest** ones.
**Analysis:** By showing that even a fitness-blind sequential search matches sophisticated methods like ShinkaEvolve, the authors provide a powerful counter-argument to the necessity of complex selection mechanisms (e.g., tournament selection, island models). This identifies a potential "over-engineering" trend in the field where the base LLM's capacity for iterative improvement is doing the heavy lifting, not the evolutionary wrapper.

### 3. Statistical Rigor and Evaluation Cascades
**Contribution:** The identification of the "Small Dataset Variance" problem in agentic scaffold design (Section 6) is a significant forensic contribution. The paper correctly notes that evaluating scaffolds on ~100 questions leads to selection bias toward stochastic outliers.
**Methodological Innovation:** The introduction of the **Probability of Dominance** and the **Evaluation Cascade** are excellent best practices for the field. They provide a principled way to reduce noise while maintaining the economic feasibility of expensive LLM-based evaluations.

## Proposed Resolution
- Quantify the impact of "random" vs "fitness-based" selection within the SCS framework to further isolate the contribution of selection mechanisms.
- Provide a more detailed breakdown of the "minimal domain knowledge" prompts to ensure that the baselines didn't benefit from hidden hints not present in the complex pipelines' prompts.
- Discuss whether the "Search Space vs. Pipeline" finding generalizes to more "open-ended" code generation tasks where the verifier is less formalized than a mathematical bound.
