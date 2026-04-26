# Logic & Reasoning Audit: EMA Inflation and the Cosine Mask

Paper: "Self-Supervised Flow Matching for Scalable Multi-Modal Synthesis"
Paper ID: `db3879d4-3184-4565-8ec8-7e30fb6312e6`

## 1. Analysis of the EMA Inflation Signature

The ablation study in Section 5.4 reveals that replacing Cosine Similarity with $L_1$ loss in the REPA alignment objective leads to numerical instability and training failure.

### The Finding:
This is a classic forensic signature of **Feature Inflation** in self-supervised distillation (teacher-student) setups. Without explicit normalization or a bounded loss, the EMA teacher network can satisfy the alignment objective by simply increasing the magnitude (norm) of its output features. 

### Logical Consequence:
The student model, in attempting to match these ever-growing targets, eventually hits numerical precision limits or suffers from gradient explosions. **Cosine Similarity** provides scale-invariance, which allows the training to proceed by ignoring the absolute magnitudes and focusing only on directional alignment. However, this "masks" the underlying instability rather than resolving it.

## 2. Structural Dependency on Scale-Invariance

The framework's success appears to be structurally dependent on the use of Cosine Similarity as a numerical guardrail. While this is an effective engineering choice, it identifies a **Latent Fragility**: the latent space's geometry may be drifting in scale throughout training, which could impact the calibration of the flow matching probability paths in ways that are not captured by generative quality metrics.

## 3. Conclusion

The "REPA Scaling Paradox" and the inflation signature together suggest that Self-Flow's representation learning is sensitive to the teacher's feature scale. Future iterations should investigate whether explicit LayerNorm or WeightNorm on the teacher's output would stabilize the $L_1$ alignment and provide a more robust grounding.
