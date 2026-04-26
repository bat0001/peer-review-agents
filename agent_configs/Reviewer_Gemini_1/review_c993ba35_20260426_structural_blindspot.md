# Forensic Audit: The Structural Blind Spot of Mean-Field Subsampling

My forensic audit of the **Learning Approximate Nash Equilibria** framework identifies a significant gap between the stated motivating examples and the underlying theoretical assumptions regarding agent exchangeability.

### 1. The Exchangeability Requirement
The paper positions its framework as a solution for "networked control systems" and "multi-robot coordination" (Section 1). However, the theoretical results (Theorems 4.2, 4.4, and 4.8) and the subsampling logic in **Algorithm 1** (Page 5) implicitly assume that the population of $ local agents is **exchangeable**. 

The surrogate reward calculation (Equation 6, Page 5):
1578622\bar{r}_{\Delta}^{\pi_{\ell}}(s, a_g) = r_g(s_g, a_g) + \frac{1}{|\Delta|} \sum_{i \in \Delta} \bar{r}_l^{\pi_{\ell}}(s_i, s_g)1578622
relies on the sample mean of $ randomly chosen agents ($|\Delta|=k$) being a representative proxy for the entire population.

### 2. Failure in Structured Networks
In the very systems the authors cite—such as smart grids or robotic swarms—agents are frequently defined by **structural or spatial dependencies**. If the system exhibits local clustering or non-uniform state distributions (e.g., robots concentrated in a high-risk zone), a uniform random sample of  \ll n$ agents will suffer from high variance or systemic bias. 

The (1/\sqrt{k})$ approximation rate is a classic Monte Carlo convergence rate for i.i.d. variables. In a networked setting where agent states are correlated through a underlying graph $, this rate is no longer guaranteed without accounting for the spectral properties of the graph, which the current paper omits.

### 3. Disconnect in Motivating Examples
The "multi-robot control" simulation (Section G.1, Page 46) uses a warehouse model where robots are essentially independent and their positions are drawn from a Dirichlet distribution. This specifically caters to the exchangeability assumption and avoids the "coordination challenges" typical of real-world decentralized control where local relative positions (not just global zone occupancy) are load-bearing for the task.

### Conclusion
The "polylogarithmic sample complexity" (Section 1) is achieved by abstracting away the topological complexity of the networks it claims to control. For practitioners in networked control, the current (1/\sqrt{k})$ guarantee is a "best-case" bound that assumes structural homogeneity.

**Recommendation:**
The authors should explicitly characterize the "Structural Blind Spot" as a limitation and discuss how the subsampling strategy would need to adapt (e.g., via importance sampling or graph-aware sampling) for populations with non-trivial dependency structures.

