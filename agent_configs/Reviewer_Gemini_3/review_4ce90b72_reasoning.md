# Reasoning for Review of Paper 4ce90b72

## 1. Analysis of the "Masked Delta Loss" (Section 3.3)

The authors propose partitioning the latent code into $z = [z_{\text{shared}}, z_{\Delta}]$ and introducing a masked delta loss:
$$ \mathcal{L}_{\Delta} = \left\| \Delta - (W_{\text{ft}} - W_{\text{base}}) \begin{bmatrix} 0 \\ z_{\Delta} \end{bmatrix} \right\|_2^2 $$
where $\Delta = b - a$ (activation difference).

**The Logic Gap (Objective Competition):**
- The standard reconstruction loss $\mathcal{L}_{\text{recon}}$ minimizes $\|a - \hat{a}\|^2 + \|b - \hat{b}\|^2$.
- If $z_{\text{shared}}$ is active, it contributes to both $\hat{a} = W_{\text{base}} z$ and $\hat{b} = W_{\text{ft}} z$.
- The reconstructed difference is $\hat{\Delta} = \hat{b} - \hat{a} = (W_{\text{ft}}^{\text{shared}} - W_{\text{base}}^{\text{shared}}) z_{\text{shared}} + (W_{\text{ft}}^{\Delta} - W_{\text{base}}^{\Delta}) z_{\Delta}$.
- **Conflict:** $\mathcal{L}_{\text{recon}}$ pressures the model to use *all* available latents (including $z_{\text{shared}}$) to explain the difference $\Delta$. However, $\mathcal{L}_{\Delta}$ explicitly forbids $z_{\text{shared}}$ from explaining $\Delta$, forcing the entire signal into $z_{\Delta}$.
- Without an explicit weight-sharing constraint $W_{\text{ft}}^{\text{shared}} = W_{\text{base}}^{\text{shared}}$, the model is in a state of "objective competition":
    - If $z_{\text{shared}}$ captures a feature that slightly shifts during finetuning (a very common occurrence), $\mathcal{L}_{\text{recon}}$ will update the shared weights to match this shift.
    - But $\mathcal{L}_{\Delta}$ will then see this as "unexplained" delta (since $z_{\text{shared}}$ is masked) and will force a $z_{\Delta}$ feature to cancel out the shared feature's shift or duplicate it.
- This leads to **latent redundancy** or **feature splitting**, where the same semantic concept is represented by both a shared and a delta latent, defeating the purpose of "model diffing."

## 2. Parameter Sensitivity and Design Choices

- The paper designates 20% of the dictionary as "shared." This is a hard-coded heuristic.
- The "BatchTopK" sparsity multiplier $\alpha = 2.0$ for shared latents (Table 2) suggests that shared structure is expected to be more "dense" than delta structure.
- While the empirical results (steering) are successful, the lack of theoretical analysis of this objective competition makes it unclear if the method is robust to features that are "partially shared" (i.e., exist in both but change significantly).

## 3. Transparency and Baselines

- The paper compares against "SAE-based diffing baselines" and "Non-SAE-based."
- However, the "Masked Delta Loss" is the primary innovation, and its interaction with the partition $z = [z_{\text{shared}}, z_{\Delta}]$ should be ablated against a version where $z_{\text{shared}}$ is NOT masked in $\mathcal{L}_{\Delta}$ but instead has a "stability penalty" (e.g., $\|W_{\text{ft}}^{\text{shared}} - W_{\text{base}}^{\text{shared}}\|^2$). This would be a more principled way to handle shared structure.
