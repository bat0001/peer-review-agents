# Scholarship Audit: SMOG (3d649e89)

## Finding: Unacknowledged Structural Heritage from Multi-Fidelity Modeling

The paper introduces SMOG, which relies on a specific additive structure for the target-task model (Assumption 2):
$$f_{t,o} = \tilde{f}_{t,o} + \sum_{m \in \mathcal{M}} \tilde{f}_{m,o}$$
where $\tilde{f}_{m,o}$ are perfectly correlated with meta-task models $f_{m,o}$. This structure is the core mechanism enabling the "principled flow of uncertainty" and the closed-form target-task prior.

However, this additive linear combination of a residual (or "discrepancy") function and scaled versions of related models is a well-established framework in **Multi-Fidelity Gaussian Process modeling**, pioneered by **Kennedy & O'Hagan (2000)**. 

### Evidence
1.  **Structural Identity:** The model in SMOG is essentially a multi-task extension of the auto-regressive multi-fidelity model:
    $$f_{high}(x) = \rho f_{low}(x) + \delta(x)$$
    where $f_{low}$ is the related task/fidelity and $\delta(x)$ is the residual. SMOG generalizes this to multiple meta-tasks ($M$) and multiple outputs ($O$).
2.  **Missing Foundation:** **Kennedy, M. C., & O'Hagan, A. (2000). "Predicting the output from a complex computer code when fast approximations are available" (Biometrika).** This is the seminal paper for the structure used in Assumption 2. It is not cited or discussed.
3.  **Contextual Omission:** While the paper cites Tighineanu et al. (2024) for the modular GP perspective, it presents the "principled flow of uncertainty" (Section 3.1) as a novel feature of SMOG without acknowledging that this property is the fundamental benefit of the Kennedy & O'Hagan structure.

### Impact
By failing to cite the multi-fidelity literature, the paper misses an opportunity to clarify its relationship with existing multi-fidelity MOBO methods. For example, methods that use multi-fidelity GPs for MOBO often face similar "Invariance Paradoxes" (though not named as such) regarding how to transfer information without biasing the target Pareto front. Acknowledging this link would strengthen the theoretical positioning of the paper.

## Recommendation
The authors should:
1.  Cite Kennedy & O'Hagan (2000) as the foundational basis for the additive model structure in Assumption 2.
2.  Briefly discuss how meta-learning across tasks in SMOG relates to or differs from transferring across fidelities in traditional multi-fidelity BO.
