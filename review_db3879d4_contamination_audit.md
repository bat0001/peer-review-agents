# Reasoning: Forensic Audit of Information Asymmetry and Feature Contamination

**Paper:** Self-Supervised Flow Matching for Scalable Multi-Modal Synthesis (`db3879d4`)

## 1. Bidirectional Contamination Risk
The "Dual-Timestep Scheduling" (DTS) mechanism relies on applying heterogeneous noise levels across tokens within a single bidirectional forward pass. 
**Audit Finding:** In a standard non-causal Transformer (like the DiT architecture typically used for flow matching), attention allows for global information exchange. This creates a "Feature Contamination" failure mode:
- High-noise tokens can attend to low-noise tokens (the intended reconstruction path).
- **Crucially**, low-noise "anchor" tokens can also attend to high-noise "target" tokens. 
By the time features reach the deeper layers where the alignment loss $\mathcal{L}_{\text{rep}}$ is applied, the clean anchor representations may have been diluted by noise from the rest of the sequence.

## 2. Co-adaptation vs. Semantic Learning
Without architectural enforcement of the information gradient (e.g., via causal masking of low-noise tokens from attending to high-noise ones), the model may simply learn to "de-mix" the noise levels or co-adapt student/teacher features. 
This is a much simpler task than the semantic reconstruction required in Masked Autoencoders (MAE). If the model "cheats" via bidirectional attention, the resulting representations may be co-adaptation artifacts of the DTS training distribution rather than robust semantic features. This would explain the potential "Vector-to-Scalar" manifold gap at inference.

## 3. Necessity of Causal-Mask Ablation
A causal-mask ablation is the only definitive way to verify if the information-asymmetry mechanism is genuinely load-bearing. By restricting attention such that anchor tokens cannot perceive target tokens, one can isolate the directional benefit of semantic reconstruction.
