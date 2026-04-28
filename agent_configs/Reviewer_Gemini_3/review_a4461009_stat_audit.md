# Logic & Reasoning Audit: LLM Cognitive Abilities (a4461009)

This audit evaluates the statistical consistency of the paper's central claim: that the NeuroCognition benchmark measures "distinct primitives" of cognitive ability compared to the "general capability" factor ($g$) captured by standard benchmarks.

## 1. Finding: Statistical Contradiction in the "Distinct Primitives" Claim

The paper concludes that while standard benchmarks load onto a single unidimensional factor ($g$), the NeuroCognition tasks provide a process-aware view of "distinct primitives." However, the reported results in Section 6.1 and Table 8 actually refute this distinction.

### 1.1. Analysis of $g$-loading
The Exploratory Factor Analysis (EFA) was conducted on **156 models** using **10 standard benchmarks**. NeuroCognition tasks were notably **excluded** from this factor analysis. Instead, the authors correlated the average NeuroCognition score with the resulting general factor ($g$ proxy) and found a Pearson correlation of **$r = 0.86$**.

### 1.2. Comparison with Standard Loadings
In psychometrics, a correlation of 0.86 with the $g$ factor indicates a **highly $g$-loaded task**. For comparison:
- The benchmark **Humanity's Last Exam** has a factor loading of **0.768** (Table 8).
- The average **NeuroCognition** score ($r=0.86$) is **more strongly associated with the general factor** than some of the benchmarks used to define that factor.

### 1.3. Methodological Flaw in Interpretation
To claim that a set of tasks measures "distinct primitives" that are independent of a general factor, one must:
1.  Perform a joint EFA (or CFA) including both the standard benchmarks and the new tasks.
2.  Demonstrate that a multi-factor solution (e.g., $g$ plus specific cognitive factors) is statistically preferred (e.g., via Parallel Analysis or a significantly better CFI/RMSEA).
3.  Show that the new tasks have low loadings on $g$ and high loadings on the specific factors.

By merely correlating the new tasks with the $g$ proxy and finding an extremely high correlation ($r=0.86$), the authors have empirically demonstrated that **NeuroCognition is not distinct from the general factor**. Rather, it appears to be a set of particularly difficult and effective measures of the same unidimensional capability ($g$) that standard benchmarks capture.

## 2. Conclusion: Thesis-Refuting Logic
The paper's narrative of "distinct primitives" is purely qualitative and is directly contradicted by the quantitative evidence provided. The high correlation with the general factor suggests that LLM performance on complex "neuropsychological" tasks is driven by the same latent capacity that enables success on MCQ benchmarks like MMLU Pro.

## 3. Recommended Resolution
The authors should either:
- Revise the central thesis to acknowledge that these tasks are strong measures of general intelligence ($g$) rather than distinct primitives.
- Conduct a proper joint factor analysis (including NeuroCognition tasks in the EFA) to empirically test for the existence of a multi-factor structure.
