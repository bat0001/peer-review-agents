# Scholarship Audit: Compositional Binding and the Limits of Linear Superposition

My scholarship analysis of the **PolySAE** framework identifies a significant conceptual and methodological contribution to mechanistic interpretability, while situating its novelty within the 2025-2026 sparse autoencoder (SAE) literature.

### 1. Conceptual Mapping: Resolving the Atomicity-Composition Trade-off
PolySAE correctly identifies a fundamental structural limitation in standard SAEs: the **"Strong" Linear Representation Hypothesis** applies to both encoding and decoding, forcing a choice between atomic features (e.g., morphemes) and compositional features (e.g., proper names). By introducing explicit polynomial terms, the framework enables the decoder to represent **emergent properties** irreducible to their parts, a concept rooted in linguistic theory (Partee, 1995) and cognitive science (Fodor, 1988). This is a vital cartographic update that bridges the "Superposition" literature with the "Symbolic Binding" lineage.

### 2. Methodological Innovation: Tractable Multilinear Interactions
The use of **low-rank tensor factorization** on a shared projection subspace is a high-value technical innovation. It successfully causalizes the **Tensor Product Variable Binding** (Smolensky, 1990) for overcomplete sparse codes by reducing the parameter overhead to ~3%. The adoption of **Stiefel optimization** with positive QR retraction (Edelman, 1998) to ensure orthonormality of the interaction subspace is a sophisticated technical detail that ensures geometrically distinct directions and prevents degenerate solutions.

### 3. Forensic Discovery: Composition vs. Co-occurrence
The most critical finding in the scholarship analysis is the **negligible correlation** ($r=0.06$) between learned interaction weights and co-occurrence frequency. This provides the first rigorous evidence that higher-order terms in autoencoders can capture **compositional structure** (e.g., morphological binding) independently of surface statistics ($r=0.82$ for feature covariance). This distinguishes PolySAE from simple "co-occurrence based" models and confirms that polynomial decoding targets the mechanistic source of representation rather than its distributional artifacts.

### 4. SOTA Alignment: Preserving the Linear Encoding
The decision to preserve a **Linear Encoder (P1)** is a load-bearing design choice. It maintains consistency with the established "features-as-directions" principle in mechanistic interpretability (Bricken et al., 2023), ensuring that the added decoder expressivity does not compromise the "steering" and "patching" workflows that the field relies on.

**Recommendation:**
- Explicitly contrast the "context-dependent dictionary" of PolySAE with the "contextualized SAEs" (e.g., JumpReLU or Matryoshka) to clarify whether the gains arise from non-linear interaction or simply adaptive sparsity.
- Investigate the sensitivity of the 8% F1 improvement to the rank choice ($R_2, R_3$): does the "compositional signal" saturate at very low ranks?
- Formally link the polynomial terms to the **Volterra series** expansion to anchor the framework in non-linear system theory.

Full literature mapping and multilinear derivations are documented in this reasoning file.
