# Reasoning: Theoretical Ill-Posedness of Unpaired Model Diffing

**Paper:** Delta-Crosscoder: Robust Crosscoder Model Diffing in Narrow Fine-Tuning Regimes (`4ce90b72`)

## 1. The Unpaired Delta Paradox
The manuscript claims in Section 3.3 that the delta objective $\mathcal{L}_\Delta$ "**does not require $a$ and $b$ to arise from matched inputs**." 
**Audit Finding:** This claim is mathematically ill-posed for sparse autoencoders. In high-dimensional Transformer activation spaces, the semantic variance between differing prompts (e.g., Prompt A vs. Prompt B) is typically several orders of magnitude larger than the subtle representational shifts induced by narrow fine-tuning. 
Attempting to reconstruct an unpaired difference $\Delta = b(X') - a(X)$ using sparse latents will inevitably cause the $z_\Delta$ dictionary to absorb task-agnostic prompt artifacts (the difference between $X$ and $X'$) rather than isolating the fine-tuning specific features.

## 2. Reconciling the Contrastive Implementation
The authors' success appears to be anchored to the **Contrastive Text Pairs** implementation (matching inputs $X = X'$), which provides a stable difference signal. The broader claim of "input-agnosticism" is not only unverified but sits in direct tension with the numerical stability required for SAE training.

## 3. RDN Contradiction
I reiterate the material contradiction regarding the **Relative Decoder Norm (RDN)**. Per Equation 4, RDN is a ratio bounded in **[0, 1]**. Reporting a value of **52.5** in Appendix F.1 for this metric indicates a fundamental failure in either the reporting or the implementation of the causal selection logic.
