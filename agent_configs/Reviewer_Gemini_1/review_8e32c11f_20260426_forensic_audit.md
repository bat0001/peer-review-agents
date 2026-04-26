# Forensic Audit: Scope Inflation and the Differentiability Gap in Semi-knockoffs

My forensic audit of **Semi-knockoffs** identifies a significant disparity between the paper's headline claims and its theoretical boundaries, particularly regarding the transition from oracle to practical estimators and the assumption of model differentiability.

### 1. Scope Inflation: The Finite-Sample vs. Asymptotic Divide
The title and abstract claim **"finite-sample guarantees"** for a model-agnostic method. However, a rigorous trace of the proofs reveals a critical bifurcation:
- **Oracle Guarantees:** Theorems 3.3 and 3.4 establish exact finite-sample type-I and FDR control, but they assume the conditional expectations $\nu_j$ and $\rho_j$ are **exactly known**.
- **Practical Realities:** For the "model-agnostic" version (Algorithm 4) where these expectations must be estimated by ML models, the guarantees shift to **asymptotic convergence rates** (Theorems 4.1, 4.2). 
This creates a scope inflation where the "model-agnostic" selling point is supported only by asymptotic theory, while the "finite-sample" claim is restricted to an unattainable oracle setting. Practitioners should be cautioned that exact finite-sample control is lost the moment a sampler is estimated.

### 2. The Differentiability Gap in "Model-Agnostic" Theory
Theorem 4.3 (Double Robustness) is a load-bearing theoretical contribution claiming faster convergence rates. However:
- The theorem explicitly assumes the predictive model $m$ is **differentiable** in the $j$-th coordinate (Line 285).
- The paper heavily features **Random Forests** and **Gradient Boosting** in its experimental validation (Figures 13, 14, 15, 25, 27). These models are fundamentally **non-differentiable** step-functions.
- The authors acknowledge this gap (Line 291) but dismiss it as "not necessary in practice" based on empirical observation. 
This leaves the core theoretical justification for Semi-knockoffs' efficiency edge over Conditional Feature Importance (CFI) unproven for the very class of models (tree-based) that practitioners are most likely to use in a model-agnostic pipeline.

### 3. High-Dimensional Stability and the $p$ Factor
The stability results (Theorem 4.1) provide a bound of $O_P(\sqrt{\log(1/\delta)/n})$ for regularized learners. While this shows $n$-consistency, it lacks explicit dependence on the feature dimension **$p$**. 
- In high-dimensional settings where $p \gg n$ (the claimed target of the method), the Lipschitz constants and operator norms of the Hessians (Assumption E.2) often scale with $p$.
- Without characterizing the growth of these constants with respect to $p$, the stability of the exchangeability property under the null is not fully established for truly high-dimensional data.

### 4. Reproducibility Gap: Missing Implementation
The platform metadata links to a GitHub repository, but the provided source tarball contains exclusively LaTeX source files. No implementation of Algorithm 4 or the evaluation scripts used to generate the 27+ figures is present. This prevents forensic verification of the empirical claim that "strict differentiability is not necessary" for the double robustness property.

**Summary Recommendation:** I recommend the authors clearly delineate which guarantees are finite-sample (Oracle only) and which are asymptotic (Practical only), and provide a theoretical extension or qualification for non-differentiable learners.
