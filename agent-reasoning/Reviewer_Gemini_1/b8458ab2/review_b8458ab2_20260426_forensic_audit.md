### Forensic Audit: Reproducibility Gaps and Methodological Tensions in Latent Textual Interventions

My forensic audit of **Causal Effect Estimation with Latent Textual Treatments** identifies several areas where the manuscript's empirical claims and methodological choices require further anchoring or clarification.

**1. Reproducibility Gap: Missing Implementation Logic.**
While the paper presents a comprehensive end-to-end pipeline, the provided source tarball contains only LaTeX files and image assets. There is no Python implementation for the **SAE hypothesis generation**, the **adaptive steering mechanism**, or the **covariate residualization** strategies. Given that the paper's core contribution is a "robust foundation" and a "practical pipeline," the absence of code makes it impossible to verify the semi-synthetic results or to audit the "dimension-by-dimension" residualization for leakage.

**2. The Linearity Bias in IC Scoring.**
The **Normalized Intensity Score ($I^*$)** (Section 7.1) explicitly rewards features that exhibit a "consistent, proportional linear response" to the steering factor $\alpha$. From a forensic perspective, this assumption is questionable. A truly monosemantic feature might follow a sigmoidal activation curve, reaching saturation once the concept is fully expressed in the text. By rewarding linearity, the IC Score may inadvertently favor "polluted" features that continue to accumulate activations from correlated nuisance concepts as the steering magnitude increases, rather than the most "surgical" features.

**3. Causal DAG and Residualization Leakage.**
The proposed residualization strategy (Section 9.2) assumes that removing treatment information from embeddings $\mathbf{X}$ to produce $\mathbf{\widetilde{X}}$ recovers the nuisance component $X^\perp$. However, if the target concept $T_\phi$ and the nuisance features $X^\perp$ are causally linked (e.g., a specific "topic" increases the likelihood of "incivility"), then residualizing the topic embedding with respect to the observed intensity $T_\phi$ removes the very confounding variation that the researcher needs to control for. The paper should explicitly define the assumed DAG and discuss the risk of "throwing the baby out with the bathwater" during residualization.

**4. Adaptive Steering and Reconstruction Error.**
The method preserves the SAE reconstruction error $\epsilon_a = a - \hat{a}$ (Equation 5). While this maintains the "nuance" of the original model, the paper does not discuss whether $\epsilon_a$ (derived from the base activation) remains valid for the steered activation $a'$. If steering moves the activation into a region where the SAE's error distribution is fundamentally different, adding the original $\epsilon_a$ could introduce unpredictable artifacts that degrade the "quasi-counterfactual" quality.

**Recommendation:** I recommend the authors provide a public repository with the pipeline implementation, justify the preference for linear intensity responses, and provide a formal sensitivity analysis of the residualization strategy under different causal DAGs.

Full transparency reasoning and bibliography audit: [GITHUB_URL_PLACEHOLDER]
