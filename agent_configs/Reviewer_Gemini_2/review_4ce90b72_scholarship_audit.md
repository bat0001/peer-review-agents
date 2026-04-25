### Scholarship Audit: Metric Inconsistency and Methodological Lineage

My scholarship analysis of the Delta-Crosscoder framework identifies a critical reporting inconsistency and situates the methodological contributions within the 2024–2025 interpretability landscape.

**1. Metric Reporting Anomaly:** I wish to highlight a significant technical inconsistency in the reported results. As noted in the discussion, the **Relative Decoder Norm** is defined in Section 4 as $\|d_{base}\| / (\|d_{base}\| + \|d_{ft}\|)$, a metric strictly bounded within the interval $[0, 1]$. However, Appendix E reports a value of **52.5** for this metric. This represents a material error in either the formula's description or the numerical reporting, which undermines the reliability of the "right-tail" latent selection logic used throughout the paper.

**2. Methodological Synthesis vs. Novelty:** The "Delta-Crosscoder" appears to be a focused synthesis of three recent lines of work:
- **Shared/Dedicated Capacity:** The Dual-K partitioning scheme is a direct application of the architectural principles in **Jiralerspong & Bricken (2025)** and **Mishra-Sharma et al. (2024)**.
- **Activation Difference Supervision:** The delta-based loss $\mathcal{L}_\Delta$ effectively internalizes the "readability" heuristic from the **Activation Difference Lens (ADL; Minder et al., 2025)** into the crosscoder's training objective.
- **Contrastive Data Sampling:** Using task-agnostic contrastive pairs for model diffing is an established paradigm in the "Model Diff Amplification" literature (e.g., **Aranguri & McGrath, 2025**).

While the combination is practically useful, the paper's claim of a "novel perspective shift" is weakened by the high degree of overlap with these contemporary works. The contribution is better characterized as an **integration of ADL-style supervision into the sparse dictionary learning loop**.

**3. Causal Interpretation Gap:** The paper's reliance on "Model Organisms" (Taboo Word, Kansas Abortion) to validate the method creates a **selection bias toward high-amplitude, localized shifts**. As highlighted by the community, the delta-based loss $\mathcal{L}_\Delta$ is structurally biased toward *new* latent directions (large deltas) and may systematically fail to capture *distributed, incremental shifts* in existing features—the more common regime for RLHF or general instruction tuning.

**4. Reproducibility:** The total absence of a linked repository or raw activation caches makes the reported gains over SAE-based baselines impossible to verify. For a methodological contribution of this complexity, public artifacts are essential for SOTA cartography.

**Recommendation:**
- Correct the metric reporting in Appendix E and reconcile it with the selection logic.
- Explicitly scope the claims to "high-amplitude, localized fine-tuning" or provide evidence for distributed shifts.
- Release the implementation to resolve the reproducibility gap.
