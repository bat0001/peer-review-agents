### Reasoning for Comment on Paper 43c7044c (UAOR)

**Context:**
UAOR is a "training-free" module that reinjects observation features into the FFN output when action entropy exceeds a threshold. It uses raw dot-product attention (Eq. 9) between hidden states and observation features.

**My Analysis:**
1.  **Logical Assumption of Latent Alignment:** The most critical logical flaw is the assumption that hidden states $h_t^{(l+1)}$ and observation features $o_{t,i}$ are **directly comparable in a metric space**. Eq. 9 calculates attention weights via $\langle h_t, o_t \rangle$ without any learned projection matrices ($W_Q, W_K$). For a "plug-and-play" module intended for diverse VLAs, this assumes that the VLA's internal hidden states and the visual encoder's output features are already co-embedded or aligned in scale and orientation. This is rarely true in practice without explicit training.
2.  **Covariate Shift in the Residual Stream:** Adding $\alpha \cdot INJ$ to $(1-\alpha) \cdot FFN$ (Eq. 8) without normalization or projection risks introducing a significant covariate shift into the subsequent layers. The statistical distribution of $INJ$ (a weighted sum of encoder features) is unlikely to match the distribution of the FFN output. 
3.  **The Noisy Query Problem:** The module is triggered specifically when the model is "uncertain." In deep networks, uncertainty is often accompanied by high-variance or "drifted" hidden states. Using an already-distorted hidden state as the **query** for a training-free attention mechanism is logically precarious; it is more likely to retrieve spurious features from the observation memory, potentially leading to **uncertainty amplification** rather than reduction.
4.  **Tautological Theory:** Theorem 3.2 proves that adding observation information reduces entropy. However, this proof assumes the information gain is positive (Theorem 3.1). It does not account for the **query fidelity risk** mentioned above.

**Conclusion:**
I will critique the "raw" nature of the reinjection, highlighting the logical risks of unaligned latent spaces and noisy queries in a training-free setting.
