# Reasoning and Evidence for Review of SurrogateSHAP (cb932990)

## Literature Mapping

### Problem Area
Data attribution for Text-to-Image (T2I) diffusion models, aiming to fairly value data contributors without the prohibitive cost of model retraining.

### Prior Work Mapping
- **Data Attribution (Influence Functions):** Seminal work (Koh & Liang, 2017).
- **Diffusion Attribution:** Related work (Park et al., 2023 - D-TRAK; Lin et al., 2024 - DAS).
- **Tree-based Explanations:** Methodology component (Lundberg et al., 2020 - TreeSHAP).
- **Compositional Diffusion:** Theoretical inspiration (Liu et al., 2022).

## Citation Audit
- `dtrak`: Real paper (2023). Metadata matches.
- `das`: Real paper (2024). Metadata matches.
- `treeshap`: Real paper (2020). Metadata matches.
- `artbench`: Real dataset (2022).
- The bibliography accurately represents the state of the field in 2024–2025.

## Analysis of Claims

### 1. Fidelity of the "Training-Free" Proxy (Section 4.1)
**Potential Vulnerability:** The central methodological shortcut in SurrogateSHAP is the assumption that the full-data conditional $p_\theta(x | c)$ can serve as a proxy for the retrained conditional $p_{\theta^*_S}(x | c)$ for all subsets $S$.
**Evidence:** Assumption 4.1 ($(\varepsilon,\varphi)$-Stability) formalizes this by assuming the RMS representation drift between the full and retrained models is bounded.
**Problem:** In deep learning, training data points interact globally during optimization. Removing a subset $N \setminus S$ doesn't just remove the ability to sample certain classes; it changes the gradient updates for shared features across *all* classes. SurrogateSHAP's proxy game (Eq. 20) only evaluates the impact of changing the mixture weights $\pi_S(y)$ on a **frozen** model's output. This reduces "contributor attribution" to "label subset valuation" at inference time, potentially ignoring the structural impact that high-quality (or adversarial) data has on the learned weights.

### 2. Attribution to Conditions vs. Data Points
**Observation:** For conditional T2I models, the proxy game evaluates the marginal utility of subsets of classes/labels. 
**Analysis:** If multiple contributors provide data for the same class (e.g., "Impressionist Paintings"), the proxy game $\hat{v}_\theta(S)$ will assign the same marginal value to their contributions as long as they are part of the same label subset. It lacks the granularity to distinguish between a "high-quality" and "low-quality" contributor within the same condition unless the "contributor" is defined as a unique condition in the model. This limits the "fair compensation" claim to the level of coarse labels rather than individual data contributions.

### 3. The GBDT Surrogate Efficiency
**Strength:** The use of GBDT as a surrogate for the utility function is a well-motivated engineering choice. It successfully transforms the combinatorial subset evaluation problem into a supervised learning task. 
**Impact:** Deriving analytical Shapley values from the tree (Section 4.2) is a computationally elegant way to leverage the TreeSHAP framework for generative model evaluation, which is otherwise extremely expensive.

## Proposed Resolution
- Acknowledge the theoretical gap between "subset-conditioned inference" and "subset-conditioned training" more explicitly in the limitations.
- Provide a validation experiment on a small, retrainable model (e.g., CIFAR-10) to quantify the correlation between the proxy Shapley values and true retraining-based Shapley values.
- Clarify whether the method can distinguish the value of different contributors who provide data for the same semantic condition.
