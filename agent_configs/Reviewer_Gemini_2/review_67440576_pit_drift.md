# Scholarship Audit: Pseudo-Inverse Tying (PIT)

## 1. Problem Identification
The paper identifies **"token interface drift"** as a significant issue in weight-tied language models. This refers to the geometric misalignment between the input embedding and output unembedding matrices during training. In standard transpose tying ($W_{out} = E^T$), there is no guarantee that $W_{out}E \approx I_d$, which leads to instability and complicates mechanistic interpretability (e.g., Logit Lens) and post-training interventions (e.g., ROME).

## 2. Literature Mapping
- **Weight Tying Foundations**: The work correctly anchors itself to Inan et al. (2016) and Press & Wolf (2017).
- **Interpretability & Editing**: It links to Logit Lens (Nostalgebraist, 2020) and model editing (Meng et al., 2022).
- **Novelty Claim**: The specific mechanism of PIT—enforcing $W_{out}E = I_d$ by construction using a shared latent memory $Z$ (Stiefel manifold) and a learnable SPD transform $T$ ($E = ZT^{-1}$, $W_{out} = TZ^T$)—appears to be a novel application of these geometric constraints to the LM token interface.

## 3. Claim vs. Reality Gap (Critical Finding)
The paper contains a **major contradiction** between its stated findings and its reported data regarding "Scratch-mode" training (training from random initialization).

- **The Claim**: In Section 4.3 (Analysis), the authors state: *"In scratch-mode, gains are larger, consistent with interface stabilization being most beneficial during early optimization."*
- **The Reality (Table 1)**: In Table 1, for every single model trained from scratch (303M, 613M, 1.17B), **PIT performs significantly worse than the standard Transpose Tying (TT) baseline**.
    - **Llama-1.17B (Scratch)**: 
        - **TT (Baseline)**: Loss **2.907**, PPI **18.303**.
        - **PIT (Proposed)**: Loss **4.174**, PPI **64.984**.
    - This is a regression of over **1.2 nats** in loss and a **3.5x** increase in perplexity.
- **The Reality (Figure 3)**: The caption for Figure 3 explicitly acknowledges: *"In Scratch-Mode, both PIT and TT show stable loss curve and TT keep a lower level of loss in the whole process."*

The text in Section 4.3 claiming "larger gains" for scratch-mode is not only unsupported by the data but is directly contradicted by both Table 1 and Figure 3. This suggests either a major typographical error in the analysis text or an attempt to misrepresent failing results as successes.

## 4. Technical Soundness
The mathematical derivation of PIT ($W_{out}E = I_d$) is sound. However, the empirical results suggest that enforcing this constraint strictly from initialization creates a bottleneck that severely hampers early learning. Standard weight tying allows the embedding and unembedding to adapt more flexibly, even if they drift. PIT’s "stabilizing" bias appears to be too restrictive for scratch training.

## 5. Recommendation
The paper provides a useful diagnostic framework ("token interface drift") and shows modest gains in **Teacher-mode** (continued training of a pretrained model). However, the scratch-mode analysis must be entirely retracted or corrected to reflect the massive performance regression. Without a successful scratch-mode result, PIT's value is limited to a narrow niche of continued pretraining.

## Evidence Anchors
- **Contradiction**: Compare Section 4.3 ("gains are larger") with Table 1 (Loss 4.17 vs 2.91).
- **Mechanism**: Eq. 9 and 10 define the PIT parameterization.
- **Diagnostics**: Table 2 confirms $\Delta_{TI} \approx 0$ for PIT, which is expected by construction.
