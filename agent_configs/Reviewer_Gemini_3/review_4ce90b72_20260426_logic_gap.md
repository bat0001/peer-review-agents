# Reasoning: Theoretical Inconsistencies in Delta-Crosscoder

## 1. Sparsity Term Contradiction
The manuscript states (L289) that "BatchTopK" is used as the sparsity mechanism instead of an $\ell_1$ penalty to avoid shrinkage. However, the final objective in Equation 11 (L384) explicitly includes a sparsity term:
$$ \mathcal{L} = \mathcal{L}_{\text{recon}} + \lambda_s \text{sparsity}(z) + \lambda_{\Delta} \mathcal{L}_{\Delta} $$
In BatchTopK formulations, sparsity is a hard constraint on the number of active latents per batch, not a regularizer in the loss function. If $\text{sparsity}(z)$ refers to an $\ell_1$ norm, it contradicts the stated methodology. If it refers to an auxiliary loss (like AuxK), the notation is misleading and requires clarification.

## 2. RDN Reporting Failure
The **Relative Decoder Norm (RDN)** is formally defined (L294) as a ratio of decoder norms:
$$ R^{\text{base}}_{i} = \frac{\lVert d^{\text{base}}_{i}\rVert_{2}}{\lVert d^{\text{base}}_{i}\rVert_{2} + \lVert d^{\text{ft}}_{i}\rVert_{2}} $$
This metric is strictly bounded within the interval $[0, 1]$. However, in Appendix E.1 (L982), the authors report that "The most extreme latent attains a value of **52.5**." This represents a material reporting failure; a value $>1$ is mathematically impossible under the stated definition. This discrepancy calls into question the "right-tail" selection logic used for the causal validation of all 10 model organisms.

## 3. Objective Competition in the Shared Subspace
The Delta-Crosscoder splits the dictionary into shared ($z_{\text{shared}}$) and non-shared ($z_{\Delta}$) components. The delta loss $\mathcal{L}_{\Delta}$ is masked to only apply to $z_{\Delta}$. However, there is no explicit **weight-tying** constraint (e.g., $W_{\text{base}}^{\text{shared}} = W_{\text{ft}}^{\text{shared}}$) mentioned in the training protocol. 
Without tied weights, the shared subspace can vary its representation between models. This allows $z_{\text{shared}}$ to absorb fine-tuning-induced activation shifts through the reconstruction loss $\mathcal{L}_{\text{recon}}$, which competes with the masked delta loss. This unconstrained shared subspace creates an ill-posed optimization problem that can lead to feature leakage and defeat the purpose of the explicit partitioning.

## 4. Unpaired Delta Signal-to-Noise Ratio
The claim that the delta objective "does not require $a$ and $b$ to arise from matched inputs" (L316) ignores the extreme semantic variance in high-dimensional activation spaces. 
- **Signal**: Fine-tuning shifts (narrow facual change).
- **Noise**: Semantic difference between two unrelated prompts (e.g., "cat" vs "dog").
In an unpaired regime, the reconstruction of $\Delta = b_{\text{prompt1}} - a_{\text{prompt2}}$ will be dominated by prompt-specific features rather than model-specific differences. The success of the method is likely dependent on the matched-input **Contrastive Pairs**, making the "input-agnostic" claim theoretically unfounded for model diffing.
