# Scholarship Audit: Delta-Crosscoder: Robust Crosscoder Model Diffing

## Summary
My scholarship audit of "Delta-Crosscoder: Robust Crosscoder Model Diffing in Narrow Fine-Tuning Regimes" identifies two primary technical inconsistencies that challenge the clarity and theoretical robustness of the proposed method.

## Detailed Findings

### 1. The Unpaired Delta Paradox
In Section 3.3 (line 316), the authors define the activation difference $\Delta = b - a$ and explicitly state that it "**does not require $a$ and $b$ to arise from matched inputs**." 

However, the auxiliary *delta loss* defined on line 382 ($\mathcal{L}_{\Delta} = \lVert \Delta - (W_{\text{ft}} - W_{\text{base}}) z_{\Delta} \rVert_2^2$) attempts to reconstruct this $\Delta$ using only the non-shared latents $z_\Delta$. Reconstructing a difference between independent random variables (unpaired inputs) is mathematically ill-posed for a sparse autoencoder, as the "input noise" (features present in one prompt but not the other) would dominate the signal. Furthermore, the "Contrastive Text Pairs" strategy described on line 341 actually produces *paired* activations from the same prompt $x$. This creates a fundamental contradiction between the general claim (that the method is task-agnostic and input-agnostic) and the actual implementation required for stable optimization.

### 2. Loss Formulation Contradiction: Sparsity Penalty vs. BatchTopK
The paper correctly identifies the limitations of $\ell_1$ sparsity in Section 3.1 and states: "**Throughout this work, we use BatchTopK as the sparsity mechanism rather than an $\ell_1$ penalty**."

Yet, the final objective function in Equation 14 (line 382) is defined as:
$$\mathcal{L} = \mathcal{L}_{\text{recon}} + \lambda_s \, \text{sparsity}(z) + \lambda_{\Delta} \, \mathcal{L}_{\Delta}$$
In a BatchTopK framework, sparsity is enforced via hard selection of $K$ latents, and an explicit $\lambda_s \, \text{sparsity}(z)$ penalty term is typically absent from the objective (unlike in traditional SAEs). The inclusion of this term, combined with the presence of an `AuxK Coefficient` in Table 1 (which is an auxiliary loss for dead features, not a sparsity penalty), suggests a potential drafting error where a standard SAE loss template was used without reconciling it with the BatchTopK implementation.

## Conclusion
Delta-Crosscoder is a promising extension of the crosscoder framework for narrow fine-tuning. However, the contradiction between the "unpaired" claim and the "contrastive" implementation, as well as the inconsistency in the loss formulation, should be clarified to ensure the method's reproducibility and theoretical grounding.
