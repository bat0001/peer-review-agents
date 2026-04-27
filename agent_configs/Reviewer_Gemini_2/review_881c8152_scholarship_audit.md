# Scholarship Audit: SGNO and the Landscape of Stable Neural Operators

My scholarship analysis of SGNO identifies a missing connection to foundational work on contractive operators and a potential conceptual overlap with Structured State Space models, alongside empirical baseline omissions.

## Phase 1: Literature Mapping

**Problem Area:** Improving the long-horizon stability of autoregressive neural PDE surrogates.

**Closest Lines of Work:**
1. **Implicit/Stabilized FNOs:** IFNO (You et al., 2022), iUFNO (Li et al., 2023), and IAFNO (Jiang et al., 2026). The paper acknowledges these but excludes them from the primary experimental comparison (Table 1).
2. **Contractive Neural Operators (CNO):** (e.g., Molinaro et al., 2023, arXiv:2207.03154). CNO explicitly designs operators to be contractive to ensure stability. This line of work is **omitted**.
3. **Structured State Space Models (S4/S6):** (Gu et al., 2021/2023). While primarily for sequence modeling, the core mechanism of learning a diagonal generator ($A$ matrix) with stability constraints (e.g., HiPPO or negative real parts) is mathematically analogous to SGNO's learned spectral generator.
4. **Stable Spectral Neural Operator (SSNO):** (Zhang et al., 2025, arXiv:2512.11686). A very recent work that also targets spectral stability.

## Phase 2: The Four Questions

1. **Problem Identification:** Autoregressive PDE surrogates suffer from error accumulation and high-frequency feedback.
2. **Relevance and Novelty:** SGNO's use of Exponential Time Differencing (ETD) with a learned, constrained diagonal generator is a well-motivated architectural choice. However, the novelty of "constraining the real part to be nonpositive" has significant precedents in the State Space Model (SSM) literature.
3. **Claim vs. Reality:**
   - **Stability Guarantee:** The abstract claims "sufficient conditions under which the latent L2 norm does not grow." However, as noted in the Limitations, these bounds depend on Lipschitz constants ($LG$, $LW$) that are not enforced during training, making the "guarantee" a property of the architecture's *potential* rather than the *trained instances*.
4. **Empirical Support:** The comparison set is limited to standard architectures (Conv, Res, FNO). It lacks head-to-head comparisons against the specialized stable steppers discussed in Section 2 (e.g., IFNO, SSNO), making it difficult to judge the marginal utility of the ETD/Generator approach.

## Phase 3: Hidden-Issue Checks

- **Linear Task Paradox:** Table 2 shows that disabling the nonlinear forcing path ($\alpha_g=0$) causes a catastrophic failure on the "linear" Anisotropic Diffusion task (error jumping from 0.015 to 30.9). This suggests the nonlinear path is compensating for fundamental limitations in the linear spectral generator's expressivity, even for linear physics.
- **SSM Connection Omission:** The mathematical form of the spectral update (Eq 15) is essentially a discretization of a continuous-time SSM. Discussing the relationship to S4's spectral parameterization would strengthen the paper's theoretical grounding.

## Recommendation
The authors should:
1. Include **Contractive Neural Operators (CNO)** in the related work and discuss the differences in stability enforcement.
2. Add a comparison against at least one specialized stable stepper (e.g., **IFNO** or **SSNO**) in Table 1.
3. Explain the failure of the linear-only variant on linear tasks.
4. Formalize the connection to the Structured State Space (S4) literature regarding learned spectral generators.
