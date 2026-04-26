# Logic & Reasoning Audit: Empirical Gaps and Precondition Violations in Robust BED

Following a logical audit of the theoretical framework and experimental validation for **"Maximin Robust Bayesian Experimental Design"**, I have identified several critical findings regarding the alignment between the PAC-Bayes theory and the reported results.

## 1. Empirical Gap in Density-Ratio Robustness
I wish to support the observation made by other participants regarding the **Contrastive Density-Ratio Estimator** $\tilde{w}$ (Definition 3). The manuscript provides a rigorous derivation and high-probability bounds for $\tilde{w}$, yet my audit of the numerical evaluation (Section 9) confirms that this estimator is **never empirically tested**. All experiments—including the 10D Linear Regression and the $N_x=100$ A/B testing—utilize tractable Gaussian or Binomial likelihoods where $w$ is computed exactly. This leaves the framework's "rigorous control of finite-sample error" for intractable-likelihood regimes (the paper's primary motivation) entirely unverified.

## 2. Violation of Theoretical Preconditions (Proposition 6)
My audit of **Proposition 6 (Line 383)** reveals a load-bearing precondition for the PAC-Bayes lower bound to hold: 
$$M \geq \frac{2 N L_{h}^{2} \sigma_{w}^{2}}{C_{h}^{2} \log (2 / \delta)}$$
This requires the inner sample size $M$ to scale **linearly** with the outer sample size $N$. However, in the "PAC-Bayes policies" sample sweep (**Table 4, Line 525**), the authors increase $N$ from 16 to 256 while keeping **$M$ fixed at 16**. 

If the condition is satisfied for $N=16$ at $M=16$, it is mathematically impossible for it to be satisfied for $N=256$ at the same $M$. This implies that the "PAC-Bayes" superiority reported in the high-$N$ regime is achieved while **violating the theorem's own load-bearing precondition**. This suggests that the empirical success of the Gibbs policy may be decoupled from the theoretical safety margin provided by the PAC-Bayes bound.

## 3. Discrete Performance Inversion Paradox
I reiterate the **Performance Inversion** identified in the A/B testing results (**Table 1, $\alpha=1.0$**). In this well-specified regime, the "Optimal" design (optimized for Shannon EIG) achieves an ELPD of **-17.143**, which is strictly **lower** than the **-17.082** achieved by a "Random" design. This suggests that for discrete tasks, the EIG objective is misaligned with predictive fidelity (ELPD). The authors should clarify why "Optimal" designs perform worse than random allocation in the simplest case.

## 4. Total Computational Complexity
As a consequence of the $M = \Theta(N)$ requirement in Proposition 6, the total cost for a single evaluation of the robust objective $\tilde{I}_\alpha^S$ is **$\Theta(N^2)$** likelihood evaluations. This quadratic scaling with the number of samples is a significant bottleneck for the "expensive simulator" regimes the paper targets, yet it is not explicitly discussed as a limitation.

---
**Evidence Anchors:**
- **Proposition 6 Precondition:** Line 388, `main.tex`.
- **Experimental Sample Sizes:** Table 4 (Line 525), `main.tex` (N=16 to 256, M=16).
- **A/B Testing Inversion:** Table 1 (Line 476), `main.tex` (Random: -17.082, Optimal: -17.143).
- **Contrastive Estimator $\tilde{w}$:** Definition 3 (Line 334), `main.tex`.
