# Reasoning for Blocked Muon Synthesis on Paper acca775c

## The Blocked vs. Concatenated Orthogonality Gap
The paper confirms (Section 5.1, Page 15) that TC models use the **ScatterMoE** backend, while ET models use a **custom PyTorch implementation**.
The Muon optimizer (Section C.1.2, Page 15) performs Newton-Schulz orthogonalization on expert weights.

### Mathematical Disparity
Let $E$ be the number of experts, and $W_i \in \mathbb{R}^{d \times d}$ be the weights of expert $i$.
1. **ET (Blocked Regime):** The custom implementation likely stores experts in a `ParameterList`. Muon is applied to each $W_i$ independently. This forces $W_i^T W_i \approx I$ for every expert.
2. **TC (Concatenated Regime):** ScatterMoE typically concatenates experts into a single $W \in \mathbb{R}^{Ed \times d}$. Muon applied to this global matrix forces $W^T W \approx I$. 
   - $W^T W = \sum_{i=1}^E W_i^T W_i \approx I$.
   - This **does not** imply $W_i^T W_i \approx I$. In fact, individual experts can be poorly conditioned or even redundant as long as their sum is stable.

## Impact on Expressivity
Individual orthogonalization (ET) is a much stronger regularizer that prevents expert collapse at the weight level. It ensures that every expert spans a diverse basis. Concatenated orthogonalization (TC) allows "lazy" experts that hide behind the better-conditioned ones.

## Symmetric Ablation Proposal
To isolate the effect of the ET routing algorithm, the authors must run a **Blocked-TC baseline**. 
If the 0.067 CE gain (Table 2) is largely driven by the optimization advantage of per-expert orthogonalization, then a TC model using the custom `ParameterList` + Muon should close the gap. Without this control, the efficiency claim is empirically ungrounded.
