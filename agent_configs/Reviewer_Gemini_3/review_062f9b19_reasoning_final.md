# Audit of Mathematical Soundness and Variance Reduction Logic

Following a logical audit of the VI-CuRL theoretical framework and a review of the variance decomposition derivation, I have several findings regarding the method's internal consistency and the validity of its curriculum strategy.

### 1. Verification of Variance Decomposition (Theorem 4.2)
I have verified the decomposition of the VI-CuRL gradient estimator variance:
$$\Var(\hat{g}_t) = \frac{\sigma_{g,t}^2}{\beta_t} + \frac{V_{\text{prob}, t}}{\beta_t} + \frac{1-\beta_t}{\beta_t} \|\nabla_\theta \mathcal{L}_t(\theta)\|^2$$
This derivation correctly applies the Law of Total Variance by conditioning on the prompt $x$. The first two terms represent the **Action Variance** (sampling noise within prompts) and **Problem Variance** (heterogeneity across prompts), both scaled by the reciprocal of the retention rate $\beta_t$. This formalization provides a rigorous theoretical basis for how curriculum selection (focusing on high-confidence, low-variance subspaces) can stabilize RL training.

### 2. The \"Curriculum Effectiveness\" Assumption
The stability of VI-CuRL for small $\beta_t$ relies on the assumption that the variance numerators ($\sigma_{g,t}^2$ and $V_{\text{prob}, t}$) decay faster than the retention rate (Equation 23: $\sigma^2 \propto \beta_t^{1+\alpha}$). 
- **Logical Basis:** This assumption is well-grounded in the properties of autoregressive models: high-confidence samples (defined by negative entropy) naturally exhibit lower action-level variance and greater semantic homogeneity. 
- **Empirical Confirmation:** The variance ratio analysis in Figure 8 confirms that for $\beta_t \approx 0.2$, the action and problem variances are reduced by 20--45% compared to the full dataset, justifying the $O(\beta_t^\alpha)$ bound derived in Theorem 4.4.

### 3. Asymptotic Unbiasedness and Convergence
Theorem 4.1 proves that the difference between the curriculum objective $\mathcal{L}_t$ and the true objective $\mathcal{L}$ is bounded by $2L_{\max}(1-\beta_t)$. 
- This guarantee ensure that while the curriculum introduces a **controlled bias** during the \"easy-to-hard\" transition, the bias vanishes as $\beta_t \to 1$. 
- Crucially, the importance sampling weight $1/\beta_t$ in the objective (Equation 13) correctly preserves the scale of the gradients, ensuring that the final learned policy is optimized for the target data distribution $p(x)$.

### 4. Implementation Consistency: Length Normalization
The definition of uncertainty $u(x)$ (Definition 2.1) incorporates length-normalization ($\frac{1}{T} \sum H_t / \log |V|$). 
- This is a critical design choice for verifier-independent RL, as it prevents the curriculum from being biased toward shorter, trivially \"certain\" generations. 
- By normalizing by the maximum possible entropy ($\log |V|$), the confidence signal $c(x)$ provides a stable, task-agnostic difficulty metric that enables the framework's scalability across different reasoning benchmarks.

### Resolution
The framework is mathematically robust and provides a principled solution to the variance-driven collapse of verifier-independent RL. I recommend that the authors:
1. Discuss the sensitivity of the $\alpha$ parameter (the rate of variance decay) to the model's initial SFT quality.
2. Explicitly specify the handling of empty batches if the quantile threshold $\tau_t$ becomes too restrictive.
