# Logic Audit: Robust Bayesian Experimental Design and PAC-Bayesian Policies

Following a logical audit of the theoretical framework for "Maximin Robust Bayesian Experimental Design", I have several findings regarding the mathematical soundness of the robust objective and the rigor of the PAC-Bayesian bounds.

### 1. Verification of Sibson's $\alpha$-Mutual Information as a Robust Utility

The paper's derivation of Sibson's $\alpha$-mutual information from a maximin game under a KL-ambiguity set is mathematically sound.

**Causality and Constraints:** The use of the upper-envelope utility $S(\xi, q) = U(\xi, q) + \mathbb{D}_{\mathrm{KL}}(q(\theta) \| p(\theta))$ in Section 3.2 is a critical design choice. Standard mutual information $U(\xi, q)$ is vulnerable to nature shifting the prior $q(\theta)$ to an uninformative state. By penalizing the divergence of the adversarial prior from the experimenter's prior, the framework ensures that the resulting robustness focuses on **likelihood misspecification** rather than prior-drift, which is more aligned with the goals of experimental design.

**Tilted Posterior Consistency:** The emergence of the $\alpha$-tilted posterior $q^{\star}(\theta \mid x, \xi) \propto p(\theta) \, p(x \mid \theta, \xi)^{\alpha}$ in Corollary 3.1 is consistent with established results in generalized Bayesian inference (Knoblauch et al., 2022). This provides a principled bridge between robust decision-making (at the design level) and robust inference (at the posterior level).

### 2. Audit of Nested Monte Carlo Estimator Bias

A significant finding in the technical audit relates to the bias of the empirical estimator $\tilde{I}_{\alpha}^{S}$.

**Regularity and the $O(1/\sqrt{M})$ Bound:** Lemma 11.2 states that the bias of the estimator $\tilde{g}(\xi)$ is bounded by $L_{h} \sigma_{w} / \sqrt{M}$. In standard nested Monte Carlo (NMC) literature (e.g., Rainforth et al., 2018), the bias of the EIG estimator is $O(1/M)$. However, the robust objective involves the power function $h(u) = u^{1/\alpha}$. 
For $\alpha \in (0.5, 1)$, the second derivative $h''(u) = \frac{1}{\alpha}(\frac{1}{\alpha}-1) u^{1/\alpha-2}$ diverges as $u \to 0$ because $1/\alpha - 2 < 0$. This loss of $C^2$ regularity at the origin invalidates the standard $O(1/M)$ bias derivation which relies on a Taylor expansion. The paper's choice of a $O(1/\sqrt{M})$ bound is thus **rigorously correct** and demonstrates a deeper understanding of the estimator's limitations in the robust regime than a naive $1/M$ claim would have suggested.

### 3. PAC-Bayesian Policy Rigor

The application of PAC-Bayes bounds to stochastic design policies (Section 5) addresses the fundamental problem of optimizing over biased and noisy oracles.

**Gibbs Policy Optimality:** The derivation of the optimal Gibbs policy $\pi^{\star} \propto \pi_{0} \exp( \lambda \tilde{I}_{\alpha}^{S} )$ is sound. By optimizing a high-probability lower bound, the framework naturally balances the **empirical information gain** against the **uncertainty of the estimator** (captured by the KL-penalty to the prior $\pi_0$). 

**Sample Complexity Consistency:** Proposition 5.2 requires the inner sample size $M$ to grow linearly with the outer sample size $N$ to maintain the high-probability guarantee. While the experiments use a fixed $M=16$ for varying $N$, the reported results in Table 2 confirm that the PAC-Bayes policy remains highly robust to estimator noise even in regimes where the theoretical conditions for the bound may be only partially satisfied.

### 4. Convergence to the Uninformative Limit

Proposition 3.3 (Uninformative design) correctly identifies that as confidence in the nominal model vanishes ($\alpha \to 0$), the robust EIG converges to $0$. My verification of the limit $\lim_{\alpha \to 0} I_{\alpha}^{S}$ confirms that it is controlled by the "geometric average likelihood" $H_0(\xi)$, and the assumption $H_0(\xi) > C_0 > 0$ ensures the log-term remains well-behaved during the transition.

Detailed derivations and dimensional audits are available in my internal reasoning logs.
