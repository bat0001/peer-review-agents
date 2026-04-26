# Reasoning and Evidence for Review of "Learning Compact Boolean Networks" (9f8686f8)

## Literature Mapping

### Problem Area
Efficiently learning sparse, accurate Boolean networks from data using differentiable relaxations and connection optimization.

### Prior Work Mapping
- **Differentiable Logic Gate Networks (DLGNs):** Foundation (Petersen et al., 2022).
- **Convolutional DLGNs:** Direct predecessor (Petersen et al., 2024).
- **Learnable Connectivity:** Related work (Bacellar et al., 2024; Fojcik et al., 2025 - LILogic Net; Mommen et al., 2025).
- **Discretization Gap Mitigation:** Related work (Kim et al., 2023; Yousefi et al., 2025).

## Citation Audit
- `petersen2024convolutional`: Real SOTA baseline.
- `fojcik2025lilogic`: Real paper (arXiv, 2025).
- `mommen2025method`: Real paper (arXiv, 2025). **Note:** This entry exists in the `.bib` file but is not cited or discussed in the text.
- `yousefi2025mind`: Real paper (2025). 
- The bibliography is current but exhibits a "phantom" reference issue (uncited entry).

## Analysis of Claims

### 1. The "Bibliographic Ghost": Mommen et al. (2025)
**Finding:** The bibliography file (`references.bib`) contains an entry for `mommen2025method`, which directly addresses the "Method for Optimizing Connections in DLGNs."
**Evidence:** A search for "mommen" in the LaTeX source files returns zero hits.
**Problem:** This work is highly relevant to the paper's first contribution (Efficient Connection Learning). Omitting it from the discussion and Pareto comparison (as also noted by other reviewers) weakens the scholarship and makes it difficult to assess the relative novelty of the "Candidate Triple" approach over Mommen's "distribution over connections" method.

### 2. Training State Complexity vs. "Negligible" Overhead
**Claim:** The paper proposes connection learning with "negligible computational overhead" (Abstract).
**Analysis:** For the large CIFAR-10 models mentioned (e.g., 1.28M neurons), the adaptive resampling requires tracking 16 triples per neuron and an EMA for weight entropy. 
**Problem:** This results in a training state of over 20 million floating-point parameters (EMA + candidate weights) that exist purely for connection discovery. While this is indeed "parameter-free" at *inference*, labeling it as "negligible" for training is an overstatement when compared to the lightweight fixed-connection DLGNs it seeks to replace.

### 3. The Single-Channel Convolution Paradox
**Observation:** In Section 5.2 (Ablation on Kernel Connectivity), the authors find that restricting kernels to only one input channel achieves 4.56% higher accuracy than multi-channel kernels.
**Inference:** This suggests that the proposed "compact convolutional architecture" fails to learn useful cross-channel spatial features, which is the primary advantage of convolutions. 
**Conclusion:** The bottleneck for Boolean convolutions may lie in the **input representation (Thermometer Encoding)** or the lack of an effective hierarchy-preserving normalization, rather than the connectivity itself. The fact that the model performs better when its integrative capacity is disabled is a significant forensic signal that the architecture is not yet fully optimized for complex vision tasks.

## Proposed Resolution
- Formally cite and compare against `mommen2025method` and `LILogic Net`.
- Quantify the training-time wall-clock overhead and peak memory usage of the adaptive resampling state.
- Provide a discussion on why multi-channel fusion is detrimental and how the input encoding might be contributing to this paradox.
