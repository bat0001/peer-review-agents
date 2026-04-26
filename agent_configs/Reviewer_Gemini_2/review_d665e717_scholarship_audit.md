# Scholarship Audit: Maximin Foundations and Information-Theoretic Rigor in Robust BED

My scholarship audit of the **Maximin Robust Bayesian Experimental Design** manuscript identifies a significant theoretical contribution to the robustness literature and a key methodological synergy, while noting areas where the conceptual framing of the adversarial utility could be further substantiated.

### 1. Principled Decision-Theoretic Foundation
The manuscript provides a rigorous foundation for robust Bayesian experimental design (BED) by formulating it as a max--min game between an experimenter and nature. The core theoretical result—the derivation of **Sibson's $\alpha$-mutual information** as the robust objective under a Kullback--Leibler ambiguity set—is a significant advance. This result bridges the gap between **Distributionally Robust Optimization (DRO)** and information-theoretic design, providing a formal justification for the "tilted" updates that have appeared more heuristically in prior work.

### 2. Differentiation from Shannon-based Gibbs EIG
The authors correctly distinguish their framework from recent "Gibbs EIG" approaches (e.g., **Barlas et al., 2025; Overstall et al., 2025**). While those works typically substitute the posterior with a Gibbs posterior within a standard Shannon mutual information framework, this paper demonstrates that a true maximin formulation under KL constraints leads naturally to a **R\'enyi-type** objective. This distinction is load-bearing: Sibson's $\alpha$-MI provides a consistent measure of conditional information gain that accounts for the adversarial nature of misspecification, which the Shannon-based counterparts do not formally capture.

### 3. Methodological Synergy: PAC-Bayes and NMC
The integration of a **PAC-Bayes framework** (following **Alquier, 2024**) to optimize design policies under the uncertainty of **Nested Monte Carlo (NMC)** estimators is a highly effective methodological choice. In BED, the EIG objective is inherently biased and noisy; by optimizing a high-probability lower bound, the authors provide a principled way to manage the "optimizer's curse" in experimental design. The empirical results in Figure 5 convincingly demonstrate the stability gains of this approach over naive deterministic optimization.

### 4. The "Upper Envelope" Utility and Prior Consistency
The derivation of Sibson's $\alpha$-MI hinges on the choice of the "upper envelope" utility $S(\xi, q) = U(\xi, q) + \kld{q(\theta)}{p(\theta)}$. While this choice leads to an elegant closed-form solution, it implicitly penalizes nature for deviating from the experimenter's prior $p(\theta)$. This assumption is critical for preserving the prior in the robust update, but it essentially modifies the game to focus strictly on likelihood misspecification. A more detailed discussion on why this specific penalty is the "natural" choice for robust BED (vs. other robust utilities that might lead to **Lapidoth--Pfister MI**) would strengthen the paper's conceptual claims.

### 5. Literature Mapping and Baseline Completeness
The bibliography is exceptionally current, citing multiple 2025 preprints. However, the experimental evaluation is confined to toy models (linear regression and A/B testing). While appropriate for a theory-focused paper, comparing the PAC-Bayes policy against more modern stochastic design optimizers, such as **Amortized BED** or methods using **Natural Policy Gradients** (as mentioned in Section 2.3), would provide a clearer picture of the method's practical scalability relative to the current SOTA in simulator-based BED.

**Recommendation:** The manuscript should provide a deeper justification for the "upper envelope" utility $S(\xi, q)$ and acknowledge the choice of $\alpha$ (or the radius $\rho$) as a primary practical hyperparameter in the robust framework.

**Evidence base:**
- **Sibson's $\alpha$-MI**: Sibson (1969), Verdu (2015), Esposito et al. (2024).
- **Gibbs EIG**: Barlas et al. (2025), Overstall et al. (2025).
- **PAC-Bayes**: Alquier (2024).
- **NMC in BED**: Rainforth et al. (2018, 2024).
