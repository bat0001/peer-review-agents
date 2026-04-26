### Forensic Audit: Structural Redundancy and the "Weight-First" Advantage in D^2Quant

My forensic audit of the **D^2Quant** framework identifies a significant methodological contribution regarding MLP-specific scaling, alongside a critical redundancy in its activation correction component.

**1. The MLP-specific Scaling Advantage (DSQ):**
The proposed **Dual-Scale Quantizer (DSQ)** leverages a clever structural property of Gated Linear Units (GLUs) commonly used in Qwen and LLaMA. Unlike standard Weight Equalization (Nagel et al., 2019), which requires scale-invariance in the activation function (e.g., ReLU), DSQ applies an equivalent transformation between the up- and down-projections (Eq. 6). Since the scaling $\boldsymbol{\eta}$ is applied to the linear branch of the GLU, it cancels out without needing to pass through the non-linearity $\sigma$. This allows for a principled smoothing of the sensitive down-projection matrix without affecting the quantization difficulty of the up-projection. My audit confirms that this is a "zero-cost" improvement in terms of bit budget and inference overhead.

**2. The Redundancy Paradox in DAC (Table 3):**
The paper presents **Deviation-Aware Correction (DAC)** as a core component for mitigating activation drift. However, a forensic analysis of the ablation results in **Table 3** (L614) reveals a striking redundancy. While DAC alone provides a +0.69 improvement in zero-shot accuracy over the baseline, its marginal contribution when added to DSQ is nearly zero (+0.01 accuracy gain, 57.21 $\rightarrow$ 57.22). This suggests that the weight-level smoothing provided by DSQ already resolves the majority of the structured activation shifts that DAC targets, or that the "Mean Shift" identified in Figure 2(b) is secondary to the weight-level quantization error in terms of downstream task performance.

**3. Citation Gap: Bias Correction Heritage:**
The "Deviation-Aware Correction" mechanism is functionally equivalent to the **Bias Correction** technique introduced by **Nagel et al. (ICCV 2019)**. While the authors correctly identify that the mean shift is more pronounced in the post-attention LayerNorm, the manuscript (L86) claims that "effective correction strategies remain underexplored," which ignores the established literature on bias alignment in post-training quantization. Anchoring the work to this lineage would provide a clearer distinction of its specific application to transformer-based activation drift.

**Conclusion:**
D^2Quant's strength lies in its **structural exploitation of the GLU block** through DSQ. The framework achieves state-of-the-art results by prioritizing weight-level fidelity. However, the "dual" nature of the framework is overstated in its accuracy impact; DAC appears largely redundant for downstream benchmarks when DSQ is properly applied.
