# Forensic Review Reasoning: RanSOM

**Paper ID:** 8dcf4132-6634-4bdd-8504-8c06c570b60f
**Title:** RanSOM: Second-Order Momentum with Randomized Scaling for Constrained and Unconstrained Optimization

## Phase 1: Foundation Audit
- **Citation Audit:** The bibliography is generally accurate and covers the relevant SOTA (STORM, SOM, Muon). Minor metadata issues (Sebbouh 2020 bib key mismatch).
- **Novelty:** The use of randomized step sizes to leverage Stein's Lemma for momentum bias correction is a novel and interesting approach to avoid auxiliary query overhead.
- **Code Audit:** No code provided.

## Phase 2: The Four Questions
1. **Problem:** Curvature-induced bias in momentum-based stochastic optimization.
2. **Novelty:** Stein-type identities for unbiased HVP estimation without auxiliary sampling.
3. **Claim vs Reality:**
    - Claim: Applicable to non-smooth ReLU networks.
    - Reality: Stein's Lemma requires absolute continuity; for step functions (ReLU gradients), the second derivative is zero a.e., while the gradient difference is non-zero. The identity fails.
4. **Empirical Support:** Strong results on Splice and MNIST1D, but activation functions are not specified, leaving the "ReLU applicability" claim unverified.

## Phase 3: Hidden-issue checks
### 1. Stein's Identity Break for Non-smooth Objectives
The paper claims in Section 3 and the Introduction that RanSOM is "applicable to non-smooth objectives like ReLU networks" (Line 134). However, the core identity (Lemma 3.1) relies on the integration-by-parts formula:
1582935\mathbb{E}[g(s) - g(0)] = \frac{1}{\lambda} \mathbb{E}[g'(s)]1582935
For a ReLU network, (s) = \nabla f(x + s d)$ is a piecewise constant function. Its derivative '(s)$ is zero almost everywhere. Thus, the RHS $\mathbb{E}[g'(s)]$ is zero. However, the LHS $\mathbb{E}[g(s) - g(0)]$ is the expected change in gradient, which is non-zero whenever the random step size $ crosses a "kink" (non-differentiable point). 

**Verification:**
Let (x) = \text{ReLU}(x)$, =-0.5$, =1$.
(s) = 1(s > 0.5)$. 
For  \sim \text{Exp}(1)$:
- LHS: $\mathbb{E}[g(s) - g(0)] = \mathbb{P}(s > 0.5) - 0 = e^{-0.5} \approx 0.606$.
- RHS: $\frac{1}{1} \mathbb{E}[g'(s)] = 0$ (since '(s) = 0$ a.e.).
Identity fails: /usr/bin/bash.606 \neq 0$.

This means RanSOM's correction term $\delta_{t+1}$ vanishes in practice for ReLU networks when using standard AD (which returns 0 for second derivatives of ReLU), reducing the method to standard momentum with randomized step sizes.

### 2. Mathematical Error in Moment Constants
In Section A.4 (Line 683), the paper claims the Stein Moment Constant {ws} = \mathbb{E}[(1 + s_t/\eta_t)^q] \le 3$ for  \le 2$ (RanSOM-E).
Let  = s_t/\eta_t \sim \text{Exp}(1)$. For =2$:
{ws} = \mathbb{E}[(1+z)^2] = 1 + 2\mathbb{E}[z] + \mathbb{E}[z^2] = 1 + 2(1) + 2 = 5$.
The claim {ws} \le 3$ is false. This propagates to the correction constant \delta$ (claimed $\approx 4.9$, actually $\approx 6.32$) and the final convergence rates.

### 3. Support vs. Local Smoothness
RanSOM-E uses an Exponential distribution with unbounded support. Assumption 4.1 (Local Geometric Smoothness) is only defined for $\|x-y\| \le 1/L_1$. The proof in Lemma C.1 does not appear to account for the probability mass of  > 1/(\rho L_1)$, where the Taylor expansion bound may not hold.
