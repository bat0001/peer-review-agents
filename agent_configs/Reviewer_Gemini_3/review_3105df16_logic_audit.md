# Logic & Reasoning Audit: DARC (3105df16)

This audit evaluates the formal rigor of the "Disagreement-Aware Alignment via Risk-Constrained Decoding" (DARC) framework, specifically focusing on the statistical properties of the primary entropic objective and the validity of the $\chi^2$-DRO bounds.

## 1. Finding: Optimistic Bias of the Plug-in Entropic Estimator $\hat{V}_\beta$

The primary decoding rule in DARC (Section 3, Eq. 3) relies on the **entropic value** $V_\beta$, defined as:
$$V_\beta(s,y) := -\frac{1}{\beta} \log \mathbb{E}[\exp(-\beta R(s,y))]$$
In practice, this is estimated using a plug-in estimator $\hat{V}_\beta$ from $n$ i.i.d. samples (style-preserving perturbations):
$$\hat{V}_\beta = -\frac{1}{\beta} \log \left( \frac{1}{n} \sum_{i=1}^n \exp(-\beta R_i) \right)$$

### 1.1. Proof of Optimistic Bias
Let $\hat{M} = \frac{1}{n} \sum \exp(-\beta R_i)$ be the sample mean of the exponential satisfaction. By linearity of expectation, $\mathbb{E}[\hat{M}] = \mathbb{E}[\exp(-\beta R)] = M$.
The estimator is $\hat{V}_\beta = -\frac{1}{\beta} \log \hat{M}$.
For $\beta > 0$, the function $f(x) = -\frac{1}{\beta} \log x$ is **convex** (since $f''(x) = \frac{1}{\beta x^2} > 0$).
By **Jensen's Inequality**:
$$\mathbb{E}[f(\hat{M})] \ge f(\mathbb{E}[\hat{M}])$$
$$\mathbb{E}\left[ -\frac{1}{\beta} \log \hat{M} \right] \ge -\frac{1}{\beta} \log \mathbb{E}[\hat{M}] = -\frac{1}{\beta} \log M = V_\beta$$
Thus, for all $\beta > 0$:
$$\mathbb{E}[\hat{V}_\beta] \ge V_\beta$$

### 1.2. Impact on Risk-Robustness
The goal of using $V_\beta$ is to introduce **pessimism** (risk-aversion) into the selection process. An estimator that is **optimistically biased** ($\mathbb{E}[\hat{V}_\beta] \ge V_\beta$) consistently overestimates the robust value of a candidate. In the low-sample regime ($n$ is small), this bias is maximized, potentially leading the model to select candidates that are perceived as robust but are actually high-variance/low-satisfaction in the tail. This undermines the "Risk-Constrained" guarantee of the framework.

---

## 2. Finding: Physical Impossibility of the $\chi^2$-DRO Bound (Prop 3.6) for Large $\rho$

Proposition 3.6 provides a mean-dispersion lower bound for a $\chi^2$-divergence ambiguity set $\mathcal{U}_\rho$:
$$\inf_{\mathbb{Q} \in \mathcal{U}_\rho} \mathbb{E}_{\mathbb{Q}}[R] \ge \mu_{\mathbb{P}} - \sqrt{\rho}\sigma_{\mathbb{P}}$$

### 2.1. Derivation and Tightness Analysis
The bound is derived via the Cauchy-Schwarz inequality on the covariance of the density ratio $h = d\mathbb{Q}/d\mathbb{P}$ and $R$:
$$\mathbb{E}_{\mathbb{P}}[hR] = \mu + \text{Cov}(h, R) \ge \mu - \sqrt{\text{Var}(h)\text{Var}(R)} \ge \mu - \sqrt{\rho}\sigma$$
The lower bound is only attainable if $h = 1 - \frac{\sqrt{\rho}}{\sigma} (R - \mu)$.
However, for $h$ to be a valid probability density, we must have $h \ge 0$ almost surely. This requires:
$$1 - \frac{\sqrt{\rho}}{\sigma} (R - \mu) \ge 0 \implies \sqrt{\rho} \le \frac{\sigma}{R_{\max} - \mu}$$

### 2.2. Vacuousness for Large $\rho$
If the ambiguity set size $\rho$ exceeds this threshold, the linear lower bound $\mu - \sqrt{\rho}\sigma$ continues to decrease with $\sqrt{\rho}$, whereas the true infimum is constrained by the support of $R$ (e.g., if $R \in [a, b]$, the infimum is at least $a$). 
In many LLM alignment settings, satisfaction is bounded (e.g., $[1, 5]$ stars). For large $\rho$, the bound in Prop 3.6 can easily become **physically impossible** (e.g., predicting a "worst-case satisfaction" of -10 for a [1, 5] range). 
The linear sensitivity to standard deviation $\sigma$ in Prop 3.6 is an artifact of the mathematical relaxation that ignores the non-negativity constraint of the probability measure $\mathbb{Q}$ for large $\rho$.

## 3. Recommended Resolutions
- **For Finding 1:** The authors should acknowledge the optimistic bias of $\hat{V}_\beta$ in low-sample regimes or propose a bias-correction method (e.g., second-order Taylor expansion correction or Jackknife).
- **For Finding 2:** The authors should specify the validity range of Proposition 3.6 or provide the constrained version of the bound that respects the support of $R$.
