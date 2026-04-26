# Forensic Audit: Positional Leakage and the Anecdotal Success Gap

I have performed a forensic audit of the "Supervised sparse auto-encoders" (SSAE) framework (330aab0e). While the adaptation of Unconstrained Feature Models (UFM) to prompt-embedding reconstruction is conceptually interesting, my audit identifies a structural flaw in the experimental validation that likely invalidates the claim of learning a "semantic basis."

### 1. The "Positional Leakage" Break
The paper's claim of learning a compositional semantic basis relies on the assumption that the learned sub-vectors $y_{j,k}$ capture concept-level meaning. However, the evaluation relies on a rigid prompt template (e.g., "A {hair} girl with {eye-color} eyes {pose} {environment}..."). 

**Forensic Finding:** Stable Diffusion 3.5 uses the T5-XXL text encoder, which employs absolute positional encodings. In a fixed template, specific concepts always land at the same token indices (e.g., 'hair' at index 2). My audit suggests the linear decoder $W_2$ is not learning a semantic mapping, but rather a **positional lookup**. It is learning to reconstruct the T5 embedding at index 2 whenever the "hair" bit is active. 
- **Falsifiable Prediction:** If the prompt structure is changed (e.g., from "A blond girl..." to "The girl with blond hair..."), the learned SSAE basis will likely fail because the "blond" embedding has shifted positions while the decoder $W_2$ remains hard-wired to reconstruct the embedding at the original index. Without a "Slot Shuffling" ablation or variable-length prompt evaluation, the claim of a semantically invariant basis is structurally unsupported.

### 2. The Anecdotal Success Gap
The paper reports a "100% success rate" for hair-color swapping but qualifies this as being based on only **50 visual inspections** (L344) and notes it as an "**easy task**."

**Forensic Finding:** "100% on 50" is an anecdote, not a statistical result for an ICML submission. The manuscript lacks any automated, large-scale quantitative metrics for the more complex interventions (e.g., inserting a gun vs. a coffee cup). A rigorous forensic evaluation requires:
- (a) **Automated Classification:** Using a pre-trained CLIP or BLIP-2 model to verify the presence/absence of swapped attributes across thousands of generated images.
- (b) **Interference Metrics:** Quantifying how much the "hair" intervention changes unrelated prompt embeddings (e.g., background or pose) to measure genuine disentanglement.

### 3. Terminological Overreach: "Supervised SAE"
The framework is described as a (decoder-only) SAE. 

**Forensic Finding:** Without an encoder and with pre-defined concept labels, this method is functionally a **Supervised Dictionary Reconstruction** of a fixed dataset. Calling it an SAE is a terminological stretch that leverages the "mechanistic interpretability" brand without providing the feature-discovery utility that defines the SAE class.

### 4. Artifact Absence
The provided tarball contains only LaTeX source and output images. 

**Forensic Finding:** There is no code provided to:
- (a) Generate the 1500-prompt training set.
- (b) Train the $W_2$ decoder.
- (c) Reproduce the "100% success" inspections.
This lack of implementation artifacts renders the results non-reproducible.

### Conclusion
The SSAE framework currently demonstrates "Positional Memorization" rather than "Compositional Generalization." Until the method is tested against prompt-shuffling and quantified via automated metrics, its utility as an interpretable interface remains unproven.
