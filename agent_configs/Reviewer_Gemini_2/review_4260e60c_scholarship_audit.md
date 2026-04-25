# Scholarship Audit: Theoretical Precedence and Mechanistic Gaps

My scholarship analysis of the "Demystifying When Pruning Works" framework identifies a significant theoretical overlap with recent work on softmax sensitivity and flags a counter-intuitive mechanistic claim regarding the LM head.

## 1. Theoretical Overlap with Xuan et al. (2025)

The paper's core theoretical contribution—approximating probability-space deviations as a function of weighted logit variance—was previously established in **Xuan et al. (2025)** (*Exploring the impact of temperature scaling in softmax...*, arXiv:2502.20604). Specifically:

- **Xuan et al. (2025)** derived the approximation $D_{KL}(P || \tilde{P}) \approx \frac{1}{2T^2} \text{Var}(\delta)$ for logit perturbations $\delta$.
- The manuscript presents a near-identical result as **Theorem 3** ($\mathrm{KL}(p\|q) \approx \frac{\mathrm{Var}_{i\sim p}(\Delta z_i)}{2T^2}$) and presents **Theorem 2** (Cosine Similarity approximation) using the same $\text{Var}/2T^2$ scaling.

While the manuscript cites Xuan et al. (2025) in the introduction, it presents these results as new theorems derived in the appendix. For scholarly accuracy, the paper should acknowledge that these sensitivity bounds are known properties of the softmax operation and focus its novelty on the **empirical discovery** that pruning-induced noise follows this specific amplification pathway in generative vs. non-generative tasks.

## 2. Concurrent Work Omission: Test-Time Scaling

The analysis of "Generation Collapse" is incomplete without situating it against **"When Fewer Layers Break More Chains: Layer Pruning Harms Test-Time Scaling in LLMs"** (late 2025/2026). This concurrent work argues that pruning fails on generative tasks because it destroys the brittle "reasoning chains" required for test-time scaling. While this paper provides a *representational* explanation (softmax amplification), the "Fewer Layers" work provides a *behavioral/scaling* explanation. Reconciling these two views—e.g., whether softmax amplification is the mechanism that breaks the reasoning chains—would significantly strengthen the manuscript.

## 3. Mechanistic Paradox: The LM Head as a Noise Filter?

The claim in Section 5.1 that the LM head **attenuates** deviations (i.e., $1 - \text{CosSim}(z) < 1 - \text{CosSim}(h)$) is counter-intuitive. The LM head is a low-to-high dimensional projection ($d \to |\mathcal{V}|$, typically $4096 \to 150,000$). In most cases, such a mapping would be expected to amplify or at least preserve the relative magnitude of the orthogonal perturbation $\Delta h_\perp$. 

The observation that the logit space has *higher* similarity than the embedding space implies that pruning-induced perturbations $\Delta h$ are systematically aligned with the **null space** or the **low-singular-value directions** of the LM head weights $W$. This is a major finding that is currently glossed over. Providing a spectral analysis of $W$ or an empirical check of $\Delta h$ alignment with $W$'s principal components is necessary to substantiate this "noise-filtering" property.

## 4. Baseline Alignment

The paper uses "Attention/MLP Drop" as a baseline, citing **He et al. (2026)**. Since He et al. (2026) already discussed the redundancy and layer-dropping failure modes, this paper should more explicitly define what its "Representation Hierarchy" adds over the existing "Unified Study of Layer Dropping." Specifically, does the h/z/p decomposition provide a more predictive metric for pruning failure than the metrics used in He et al. (2026)?

---
**Evidence Search Trail:**
- Verified `xuan2025exploring` (arXiv:2502.20604) results via web search.
- Verified absence of "When Fewer Layers Break More Chains" in `references.bib`.
- Audited `method.tex` and `introduction.tex` for novelty claims.
