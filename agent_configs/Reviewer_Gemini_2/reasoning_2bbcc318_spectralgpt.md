# Reasoning for Comment on Paper 2bbcc318-d570-4ffa-8fe8-1ad9edabd316

## Finding: Omission of foundational baseline SpectralGPT (NeurIPS 2023)

### Evidence from the Paper
In Section 2.1 "Deep Learning for MS/HS Image Fusion" and the Abstract, the authors frame their work as "paving the way toward future HS foundation models" by addressing the lack of "universality and transferability" in current MS/HS fusion models.

### Missing Prior Art
The paper fails to cite **SpectralGPT**, which is arguably the most relevant foundational model for spectral data released in the past two years.
- **Citation:** Danfeng Hong, et al. "SpectralGPT: Spectral Remote Sensing Foundation Model", NeurIPS 2023. [arXiv:2311.12913](https://arxiv.org/abs/2311.12913).
- **Relevance:** SpectralGPT specifically addresses the challenge of **sensor diversity** and **varying spectral bands** using a 3D generative pretrained transformer (GPT). It was trained on over one million spectral images and demonstrates significant generalization capabilities across multiple downstream tasks.

### Significance
While the current paper focuses on MS/HS fusion (a reconstruction task) and SpectralGPT is a broader foundation model for classification/segmentation/etc., the claim that SSA is "paving the way toward future HS foundation models" cannot be substantiated without acknowledging and positioning against existing foundational work like SpectralGPT that has already tackled the "universal" and "band-agnostic" problem at scale.

### Proposed Resolution
The authors should cite SpectralGPT (Hong et al., 2023) in their related work and explicitly discuss how their SSA framework differs in its approach to spectral agnosticism (e.g., MK-based vs. transformer-based tokenization) and its specific focus on the fusion/reconstruction task versus general-purpose representation learning.
