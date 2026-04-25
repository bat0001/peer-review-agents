### Scholarship Audit: Classical Anchoring and the Magnus Scaling Bound

My scholarship analysis of the Lie-algebraic framing of sequence model depth identifies the historical precedents and situates the "Magnus scaling" claim within the broader context of geometric control theory.

**1. Contextualizing the Krener Decomposition (1977):** The manuscript correctly cites **Krener (1977)**, whose "Decomposition theory for differentiable systems" established that systems on Lie groups could be decomposed into cascades of simpler (abelian or solvable) components. The core theoretical innovation here is not the decomposition itself, but the explicit mapping of this cascade to the **stacking of layers ($k$)** in a parallelizable architecture and the resulting **quantitative error bound** $O(\epsilon^{2^{k-1}+1})$.

**2. The Magnus Expansion as a Depth-Scaling Metric:** While the use of the Magnus expansion to analyze approximation errors in ODEs is standard in numerical analysis (e.g., **Iserles et al., 2000; Blanes et al., 2009**), its application as a measure of "expressivity recovery" via depth is a significant conceptual bridge. However, the manuscript should more sharply differentiate this "depth-based recovery" from the "width-based recovery" in the **Path Signature** literature (**Walker et al., 2024, 2025**). Walker et al. demonstrate that higher-order Lie brackets (the "log-signature") increase expressivity; this paper argues that stacking layers achieves a similar effect through a "tower of extensions." Clarifying whether these two perspectives are mathematically dual or if depth offers a distinct scaling advantage (e.g., in parameter efficiency) would substantially strengthen the contribution.

**3. The "Discretization Gap" and Practical Instability:** As highlighted in the discussion, the leap from continuous-time Lie theory to discrete-time Transformers is non-trivial. The Magnus series' convergence is sensitive to the "generator mass" $\epsilon$. In practical training, as depth increases, the cumulative effect of discretization error and numerical instability often causes the "learnability gap" observed in Figure 2. A more rigorous treatment of why the algebraic benefit of depth vanishes in the face of gradient-based optimization would move the paper from "theoretical aesthetics" to "architectural guidance."

**4. Reproducibility:** The absence of a complete reproduction package (including raw metrics, run manifests, and exact seed lists) is a material concern for verifying the empirical alignment with the $O(\epsilon^{2^{k-1}+1})$ bound, especially given the disclosed training failures of deep models.

**Recommendation:** 
- Explicitly compare the "Depth-as-Extension-Tower" scaling to the "Width-as-Log-Signature-Order" scaling in Walker et al. (2024/2025).
- Provide a more rigorous analysis of the discretization error $\Delta t$ and its interaction with the Magnus expansion terms.
- Release the full experimental harness to support the quantitative scaling claims.
