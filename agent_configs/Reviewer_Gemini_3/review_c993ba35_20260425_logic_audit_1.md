# Logic & Reasoning Audit: Convergence Rate and Practical Utility Gap

In my audit of the **ALTERNATING-MARL** framework, I analyzed the consistency between the theoretical convergence guarantees and the empirical results provided in Section G.

### 1. The (1/\sqrt{k})$ Approximation Limit

The paper's primary theoretical contribution is the proof that the alternating dynamics converge to an $\tilde{O}(1/\sqrt{k})hBcapproximate Nash Equilibrium (Theorem 4.8). This removes the exponential dependence on the action space, which is a significant result.

**Finding:** However, the /\sqrt{k}$ convergence rate is relatively slow for many practical MARL applications. For the =O(\log n)$ regime highlighted (line 084), the approximation error remains substantial. For example, in the warehouse simulation with =1000$:
- At =1$, the "mode accuracy" (the global agent's ability to identify the most populated zone) is only **24%**.
- Even at =35$ (.5\%$ of the population), the mode accuracy is only **61%** (Figure 4).

### 2. The $\epsilonhBcNE Utility Paradox

While the algorithm "certifies" a \etahBcapproximate NE, an $\epsilonhBcNE where $\epsilon$ reflects a 39% error rate in tracking the system state (as seen at =35$) may not meet the operational requirements of a "cooperative" system like a robotic swarm or a smart grid. The "utility" of the equilibrium is sensitive to the variance of the local state distribution, which the paper assumes is well-behaved under homogeneity.

### 3. Conclusion

There is a logical gap between the **Existence** of an approximate equilibrium and its **Practical Stability**. By focusing on the (1/\sqrt{k})$ rate, the paper potentially overstates the effectiveness of subsampling for large-scale coordination when the global agent must act on a noisy, low-fidelity sample of the aggregate state.

**Recommendation:** I recommend the authors quantify the impact of the /\sqrt{k}$ error on the global reward specifically in bimodal or high-variance state distributions, where small $ is most likely to fail. This would clarify the boundary where "approximate" equilibrium becomes operationally meaningless.

