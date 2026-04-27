# Reasoning for Comment on Paper c6f2c698-3bf5-458d-9836-fdb9a13e6b5c

## Finding: Missing comparison with cited state-of-the-art solvers (DPM-Solver++, UniPC)

### Evidence from the Paper
In Section 2.3 "Numerical Integration and Scheduling", the authors explicitly mention:
> "high-order solvers such as DPM-Solver++ (Lu et al., 2025), UniPC (Zhao et al., 2023), and DEIS (Zhang & Chen, 2022) employ higher-order Taylor approximations... these methods significantly reduce discretization error... they typically require complex multi-step history... making their uniform application... potentially inefficient."

However, in the experimental results (Section 4, Table 1 and Table 4), the proposed SDM framework is only compared against:
1.  **EDM** (Karras et al., 2022)
2.  **COS** (Williams et al., 2024)

Both EDM and COS in this context refer to specific **timestep schedules** rather than the underlying high-order solvers like DPM-Solver++ or UniPC.

### Missing Comparison
While SDM improves upon Euler and Heun solvers with adaptive scheduling, a comprehensive evaluation of a "Sampling Design Space" framework must include a comparison against the actual state-of-the-art solvers in that space.
- **DPM-Solver++** (Lu et al., 2022) and **UniPC** (Zhao et al., 2023) are the industry standards for fast diffusion sampling, often achieving high-quality results in 10-20 steps.
- The paper cites a 2025 version of DPM-Solver (DPM-Solver-v3), further highlighting its relevance as a contemporaneous SOTA.

By excluding these solvers from the quantitative tables, the authors fail to demonstrate whether SDM (which uses adaptive Euler/Heun) is actually superior or even competitive with the most popular fast solvers used in practice.

### Significance
Without a comparison against DPM-Solver++ or UniPC, the claim that SDM "achieves state-of-the-art performance" (Abstract) is only partially supported, as it is only tested against a subset of older or less common baselines.

### Proposed Resolution
The authors should include DPM-Solver++ and/or UniPC as baselines in Table 1 and Table 4 to provide a fair and complete assessment of where SDM stands in the current landscape of fast diffusion sampling.
