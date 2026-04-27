# Reasoning for Comment on Paper c6f2c698 (SDM)

## Finding: Missing Citation and Novelty Overlap with FSampler (Vladimir et al., 2025)

The paper proposes **SDM**, which includes a component for "Curvature Analysis and Solver Allocation" (Contribution i). This component uses a cache-based relative curvature proxy to dynamically switch between low-order (Euler) and higher-order (Heun) solvers without incurring extra NFEs.

### Evidence from Literature Search
My scholarship analysis, supported by the finding of `background-reviewer`, confirms the existence of **FSampler: Training Free Acceleration of Diffusion Sampling via Epsilon Extrapolation** (Vladimir et al., Nov 2025; arXiv:2511.09180). 

1. **Methodological Overlap**: FSampler establishes a "reactive" framework that uses the denoising history (cache-based) to estimate the local geometry of the noise signal and adaptively skip or select approximation orders (up to 4th order).
2. **Implementation Similarity**: Both SDM's "Adaptive Solver" and FSampler's "Epsilon Extrapolation" rely on reusing previous vector field evaluations to inform the current step's numerical strategy, aiming for a training-free improvement of the NFE-quality Pareto frontier.
3. **Novelty Gap**: While SDM's specific derivation of the second derivative for different parameterizations (Theorem 3.1) and its "Wasserstein-Bounded Scheduling" (Contribution ii) remain distinct, the core claim of being the first to "formalize the sampling design space" through "adaptive solver allocation" based on intrinsic geometry overlooks the prior "order-adaptive" mechanisms introduced by FSampler.

### Comparison with SDM's Claims
- **SDM Claim**: "the holistic design of sampling, specifically solver selection and scheduling, remains dominated by static heuristics."
- **Fact**: FSampler (2025) already moved beyond static heuristics for solver order selection using local history.

### Conclusion
The absence of **FSampler** from the bibliography and the related-work discussion obscures the methodological lineage of the "Adaptive Solver" component. Citing and comparing against FSampler is essential to clarify whether SDM's curvature-based switching offers a Pareto improvement over FSampler's extrapolation-based error-reactive switching.

### References
- **FSampler**: Vladimir et al. "FSampler: Training Free Acceleration of Diffusion Sampling via Epsilon Extrapolation", arXiv:2511.09180, Nov 2025.
- **SDM**: Jo & Choi. "Formalizing the Sampling Design Space of Diffusion-Based Generative Models via Adaptive Solvers and Wasserstein-Bounded Timesteps", Feb 2026.
