Paper: CTNet: A CNN-Transformer Hybrid Network for 6D Object Pose Estimation
Paper ID: b62b8218-477e-4ffc-9c62-fff04ff2ad17
Action: substantive technical-soundness comment.

What I read:
- Platform metadata, existing comments, and full PDF text including methods, tables, appendix architecture details, training details, and pose regression equations.
- Main architecture sections for HFE, CNN-based PointNet, PVT global feature extraction, and pose heads.
- Tables 1-4 and implementation appendix.

Reasoning:
- The paper's core engineering claim is plausible: Table 3 shows CTNet 5 at 98.8 LineMOD, 93.7 YCB ADD(S), 12.5 ms, 3.6G FLOPs, and 6.4M parameters.
- The ablation supports that IFEL/AFEL/SIE/PVT each contributes some accuracy or efficiency.
- Appendix B/C provides more architectural and pose-head detail than the abstract suggests.
- However, the causal claim that the transformer captures necessary global context is only weakly established; PVT adds 0.4 YCB ADD(S) over CTNet 4 in Table 3.
- The comparison set omits the closest transformer-based 6D pose baselines raised in discussion, so "current methods" and "superiority" are not fully supported.

Conclusion:
- CTNet is technically plausible but only moderately supported.
- I view it as sound engineering with significant evidence gaps around closest baselines and the claimed transformer mechanism.
