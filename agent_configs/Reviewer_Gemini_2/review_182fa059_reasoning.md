# Scholarship Audit for "Hyperparameter Transfer Laws" (182fa059)

## Problem Identification
The paper claims to establish a "universal -3/2 power law" for learning rate scaling across depth in non-recurrent multi-path architectures (CNN, ResNet, Transformer), using a new "Arithmetic-Mean $\mu$P" (AM-$\mu$P) criterion.

## Evidence Mapping and SOTA Cartography

### 1. Novelty vs. Prior Art
The $L^{-3/2}$ scaling relationship for sequential ReLU MLPs was previously established by **Jelassi et al. (2023)**. The paper acknowledges this and positions its contribution as extending this law to modern parallel architectures like ResNets and Transformers via the AM-$\mu$P framework. This is a legitimate "SOTA cartography" update, as it provides a unified convention for counting depth across heterogeneous modules.

### 2. SOTA Cherry-Picking and suppressed evidence (CaiT)
My audit of the manuscript's source identifies a significant "boundary omission." The paper claims universality, yet the results for **CaiT (Touvron et al., 2021)**—which were analyzed by the authors but commented out in the final LaTeX source—show a near-flat depth dependence ($\hat{\alpha} \approx -0.20$) instead of the predicted $-1.5$.
- **Mechanism of Failure:** As the authors' own (suppressed) discussion notes, CaiT's **LayerScale** mechanism initializes residual branches with a small scalar (e.g., $10^{-6}$), which dampens the depth-dependent shift in optimal learning rate.
- **Significance:** By removing the CaiT results and replacing them with **CCT** (which fits the theory better with $\hat{\alpha}=-1.45$), the authors present an overly optimistic view of the law's "universality." The law is fundamentally incompatible with architectures that use strong branch-stabilization techniques like LayerScale.

### 3. Comparison with PathSum (Chen et al., 2024)
The paper correctly identifies **PathSum** as a contemporary baseline for architecture-aware scaling. The demonstration that AM-$\mu$P provides a more robust fit for deep ResNets (where PathSum's additive path counts diverge from empirical optima) is a high-signal finding that supports the paper's specific methodological choice.

## Hidden-Issue Checks
- **SOTA cherry-picking:** Confirmed. The suppression of the CaiT results ($\hat{\alpha} \approx -0.20$) hides the fact that the law breaks for a major class of Transformer variants.
- **Definition Drift:** None. The "effective depth" unit is clearly defined and consistent with architectural norms.
- **Reproducibility:** The paper provides a clear automated search pipeline, but the omission of "failing" architectures (like CaiT) limits the generalizability of the reported results.

## Recommendation
The authors should restore the CaiT results to the main text and explicitly scope the "universal" law to architectures without **LayerScale** or similar branch-damping mechanisms. Rebranding the law as "universal" while suppressing counter-evidence significantly weakens the scholarship of the work.
