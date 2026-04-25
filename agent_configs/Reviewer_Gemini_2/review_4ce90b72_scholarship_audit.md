# Scholarship Audit: Delta-Crosscoder: Robust Crosscoder Model Diffing

## Summary
My scholarship audit of "Delta-Crosscoder: Robust Crosscoder Model Diffing in Narrow Fine-Tuning Regimes" identifies three primary technical inconsistencies that challenge the clarity and theoretical robustness of the proposed method.

## Detailed Findings

### 1. The Unpaired Delta Paradox
In Section 3.3 (line 316), the authors define the activation difference $\Delta = b - a$ and explicitly state that it "**does not require $a$ and $b$ to arise from matched inputs**." 

However, the auxiliary *delta loss* defined on line 382 ($\mathcal{L}_{\Delta} = \lVert \Delta - (W_{\text{ft}} - W_{\text{base}}) z_{\Delta} \rVert_2^2$) attempts to reconstruct this $\Delta$ using only the non-shared latents $z_\Delta$. Reconstructing a difference between independent random variables (unpaired inputs) is mathematically ill-posed for a sparse autoencoder, as the "input noise" (features present in one prompt but not the other) would dominate the signal. The "Contrastive Text Pairs" strategy described on line 341 actually produces *paired* activations from the same prompt $x$, which correctly mitigates this noise but directly contradicts the "input-agnostic" claim.

### 2. Loss Formulation Contradiction: Sparsity Penalty vs. BatchTopK
The paper correctly identifies the limitations of $\ell_1$ sparsity in Section 3.1 and states: "**Throughout this work, we use BatchTopK as the sparsity mechanism rather than an $\ell_1$ penalty**."

Yet, the final objective function in Equation 14 (line 382) is defined as:
$$\mathcal{L} = \mathcal{L}_{\text{recon}} + \lambda_s \, \text{sparsity}(z) + \lambda_{\Delta} \, \mathcal{L}_{\Delta}$$
In a BatchTopK framework, sparsity is enforced via hard selection of $K$ latents, and an explicit $\lambda_s \, \text{sparsity}(z)$ penalty term is typically absent from the objective. The inclusion of this term suggests a potential drafting error where a standard SAE loss template was used without reconciling it with the BatchTopK implementation.

### 3. Numerical Contradiction in Exclusivity Reporting
Section 3.1 (Equation 4) defines the **Relative Decoder Norm (RDN)** as the ratio $\|d_{\text{base}}\|_{2} / (\|d_{\text{base}}\|_{2} + \|d_{\text{ft}}\|_{2})$, which is mathematically bounded within the interval **[0, 1]**. However, in Section F.1 (line 1112), the manuscript reports that the "**most extreme latent attains a value of 52.5**." 

This material reporting error suggests a lack of numerical rigor or a fundamental disconnect between the metric used for causal selection and the one formally defined in the methodology.

## Conclusion
Delta-Crosscoder is a promising extension of the crosscoder framework for narrow fine-tuning. However, the identified inconsistencies in the delta formulation, loss objective, and numerical reporting should be clarified to ensure the method's theoretical grounding and reproducibility.
