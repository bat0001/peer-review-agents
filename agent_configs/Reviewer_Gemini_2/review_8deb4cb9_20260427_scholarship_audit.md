# Scholarship Audit - ART for Diffusion Sampling (8deb4cb9)

## 1. Problem Area Mapping
The paper addresses the **Diffusion Sampling Timestep Scheduling** problem.
The goal is to find an optimal sequence of timesteps $\{\tau_k\}$ to minimize discretization error for a fixed computational budget (NFE).

### Closest Lines of Prior Work:
1. **Hand-crafted Schedules (Heuristics):**
   - **EDM (Karras et al., 2022):** Uses a power-law schedule $\sigma(t) \propto (t_{max}^{1/\rho} + \dots)^\rho$ with $\rho=7$. This is the primary baseline.
   - **DDIM (Song et al., 2021):** Linear/Quadratic schedules.
2. **Data-Driven Schedule Optimization:**
   - **Align Your Steps (Sabour et al., NVIDIA, 2024):** Minimizes local truncation error (LTE) using model-specific score information. [arXiv:2404.14507]
   - **HSO: Hierarchical Schedule Optimization (Zhu et al., 2025):** Optimizes noise schedules via bi-level optimization and LTE analysis. [arXiv:2502.13110]
   - **AutoDiffusion (Li et al., 2023):** Uses evolutionary search for time step sequences. [arXiv:2305.14707]
3. **Continuous-Time Reinforcement Learning (CTRL):**
   - **Wang et al. (2020), Jia & Zhou (2022):** Foundational theory used in the current paper.
   - **ZC24/ZC25 (Zhao et al.):** Applied CTRL to diffusion *fine-tuning* (Score as Action).

## 2. Claim vs. Reality Assessment
**Claim:** "To our best knowledge, this is the first paper that develops a principled approach to scheduling timesteps for generative diffusion sampling." (Section 1, lines 134-141)

**Reality:** This claim is **substantially overblown**.
- **Align Your Steps (AYS; NVIDIA, 2024)** introduced a principled, data-driven framework for finding optimal noise schedules by minimizing discretization error (LTE) nearly two years before this submission.
- **HSO (2025)** also provides a principled, hierarchical optimization of the schedule based on LTE.
- The authors' claim of being "first" ignores these foundational works in the optimized-sampling space.

## 3. Methodology Audit: RL Over-Engineering
- The paper uses a complex actor-critic CTRL framework to learn a state-dependent control $\theta(t, x, \psi)$.
- However, in Section 4.2 and Section 5.1, the authors admit that the policy collapses to a time-only schedule and they **distill** it into a fixed 1D grid for inference.
- **Critical Question:** If the final result is a fixed 1D grid, why is RL (which is designed for state-dependent decision making) necessary? Methods like AYS or HSO optimize the 1D grid directly and likely more efficiently.
- The paper lacks an ablation comparing the RL-based schedule discovery against a simple grid search or gradient-based optimization of the 1D grid using the same LTE proxy $|Q|$.

## 4. Empirical Support and Baseline Gaps
- **Missing Baseline:** **Align Your Steps (AYS)**. Since AYS is the most prominent "optimized schedule" method and also uses LTE minimization, its omission is a significant gap. A comparison is needed to show if ART-RL's RL-derived schedule is any better than AYS's calculus-derived schedule.
- **Heun vs. Euler:** The theory is for Euler, but the main results use Heun. While this shows robustness, it also means the "principled" part of the optimization (Equation 8) is slightly misaligned with the actual solver used.

## 5. Summary of Findings
- **Novelty Gap:** The "first principled approach" claim is factually contradicted by NVIDIA's **Align Your Steps (2024)**.
- **Rebrand/Methodological Risk:** The application of RL to find a 1D schedule appears to be an over-engineered application of the authors' previous CTRL framework to a problem that may be more elegantly solved by direct optimization.
- **Missing Context:** The paper does not discuss the relationship between its error surrogate $Q$ and the discretization error terms analyzed in AYS or EDM.
