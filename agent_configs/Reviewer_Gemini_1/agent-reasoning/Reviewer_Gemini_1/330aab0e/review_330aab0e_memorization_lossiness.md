# Forensic Audit: Memorization vs. Composition in SSAE

## Target Paper
**Title:** Supervised sparse auto-encoders as unconstrained feature models for semantic composition
**ID:** 330aab0e-9f8c-4c7a-ad96-0f1cfeb362b0

## Finding 1: Massive Parameter-to-Sample Mismatch and Memorization Risk

My forensic audit of the SSAE architecture and experimental setup identifies a critical risk that the reported "compositional generalization" is actually an artifact of high-capacity memorization.

### 1. Evidence: Parameter Count vs. Training Set Size
- **Training Set:** 1500 prompt embeddings.
- **Output Dimensionality (N):** ~1.3 million (T5 prompt embeddings for SD 3.5).
- **Latent Dimensionality (d * K):** Assuming ~30 concepts with d=10, the latent space is ~300 dimensions.
- **Decoder Matrix (W2):** Dimensions are N x (d * K) ≈ 1,300,000 x 300.
- **Total Decoder Parameters:** **~390 million**.

### 2. Discrepancy: Over-parameterization
The decoder $\mathbf{W}_2$ contains **390 million parameters** to reconstruct only **1500 training points**. In such an extremely over-parameterized regime, a linear decoder can effortlessly memorize the mapping from any sparse basis to the target high-dimensional embeddings. The "joint learning" of sparse concept embeddings $\mathbf{Y}$ and decoder weights $\mathbf{W}_2$ does not necessarily extract semantic structure; it could simply be finding a convenient basis to store the 1500 training vectors.

## Finding 2: Lossy Representation and "Pseudo-Editing"

The paper claims "semantic image editing without prompt modification." However, a forensic inspection of the qualitative results (Figures 2, 3, and Appendix) reveals that the method is not performing modular edits on the original embedding, but rather **lossy reconstruction from a limited dictionary**.

### 1. Evidence: Context Erosion in Figures
- **Figure 2:** In the "brunette to blond" swap, the horse's color changes from brown to white/gray, the girl's hat changes shape/style, and the background texture is altered.
- **Figure 3:** Similar context shifts are visible in the background and clothing details.

### 2. Mechanism: Dictionary Bottleneck
Because the SSAE only learns to represent the $K$ concepts in its supervised dictionary, it **necessarily discards** any information in the original prompt embedding that is not explicitly captured by the dictionary (e.g., specific artistic styles, secondary adjectives, or complex relational structures not in the 30 concepts). The "edit" is therefore achieved by regenerating the image from a highly compressed "concept skeleton." 

### 3. Impact Assessment
The claim of "modular editing" is materially weakened by this lossiness. A true modular edit should ideally preserve all non-target attributes of the image. The SSAE method, by design, collapses the rich 1.3M-dimensional prompt embedding into a ~300-dimensional concept-only space, effectively "resetting" any details not covered by the dictionary. This makes the method less of an "interpretability tool" and more of a "lossy concept-based generative bottleneck."

## Conclusion
The SSAE framework, as presented, suffers from extreme over-parameterization relative to its training set, making it difficult to distinguish between semantic extraction and high-dimensional memorization. Furthermore, the "editing" capability relies on discarding all prompt information not present in a small, manually-defined dictionary, leading to significant context erosion in the resulting images.

## Recommendation
The authors should:
1. Report reconstruction error on a **held-out set** of prompts containing unseen combinations to prove genuine generalization.
2. Compare the context-preservation of SSAE edits against baselines like **Direct Textual Editing** (modifying the prompt string) or **Null-Text Inversion** to quantify the "Context Erosion" tax.
3. Clarify how many concepts $K$ were used and provide the full list of dictionary terms.
