# Logic & Reasoning Audit: Parameter-Space Noise in RLVR

Following a formal audit of the PSN-RLVR theoretical framework and the proposed adaptive noise scheduler, I have identified a potential metric inconsistency and a concern regarding the stability of off-policy correction in high-dimensional LLM parameter spaces.

## 1. Divergence Direction in Self-Certainty Metric

**Finding:** Equation 8 (Page 5) defines "Self-certainty" as the mean KL divergence from the uniform distribution $U$ to the model distribution $p_{\pi_\theta}$:
$$Self\text{-}certainty(o | q) = \frac{1}{|o|} \sum_{i=1}^{|o|} KL(U \parallel p_{\pi_\theta}(\cdot | q, o_{<i}))$$

**Logical Audit:** 
In information theory, $KL(U \parallel P) = \sum_v \frac{1}{V} \log \frac{1/V}{P(v)} = -\log V - \frac{1}{V} \sum_v \log P(v)$. This quantity is the **cross-entropy** of $P$ relative to $U$, which is minimized when $P$ is uniform and grows as $P$ becomes sharper. However, $KL(U \parallel P)$ is extremely sensitive to the "tail" of the distribution $P$; if any token $v$ has a very low probability $P(v) \approx 0$, the $1/P(v)$ term explodes. 

In contrast, the standard measure of "concentration" or "certainty" is the divergence from the model to the uniform distribution, $KL(P \parallel U) = \log V - H(P)$, where $H(P)$ is the entropy. This direction is numerically stable and directly relates to the information gain. By choosing $KL(U \parallel P)$, the authors' metric may be disproportionately influenced by the least likely tokens in the vocabulary rather than the model's confidence in its primary predictions. The authors should clarify if $KL(P \parallel U)$ was intended, or justify the use of the $U$-weighted penalty.

## 2. Importance Sampling Stability in 7B Parameter Spaces

**Finding:** The framework uses Truncated Importance Sampling (TIS) with a clipping constant $C=10$ to correct the mismatch between the noisy sampler $\tilde{\pi}$ and the clean policy $\pi$.

**Logical Audit:** 
1. **The Log-Prob Sensitivity Gap:** For a 7B parameter model, a weight perturbation of $\sigma = 0.005$ (the "moderate" level in Section 4.2) is substantial. In deep neural networks, the sensitivity of the log-probability $\log \pi_\theta(o|q)$ to parameter shifts $\Delta \theta$ is governed by the Fisher Information Matrix. Given the high dimensionality, even a small $\Delta \theta$ can lead to massive shifts in the output distribution (the "curse of dimensionality" in parameter space).
2. **Weight Collapse:** If $\pi_\theta$ and $\pi_{\tilde{\theta}}$ diverge significantly, the importance weights $w_t$ will frequently hit the truncation limit $C=10$ or collapse to nearly zero. This results in highly biased gradient updates where the "exploratory" rollouts are either ignored or capped at an arbitrary magnitude. The paper lacks an analysis of the **effective sample size (ESS)** or the frequency of clipping, which is critical for verifying whether the "off-policy correction" is actually functional or if the model is simply training on a heavily biased subset of the noisy rollouts.

## Recommendation for Resolution:
1. Verify the intended direction of the KL divergence in the self-certainty metric and analyze its numerical stability compared to entropy-based measures.
2. Provide statistics on the importance weight distribution (e.g., % of weights clipped, variance of $w_t$) to substantiate the stability of the TIS-GRPO integration.
3. Clarify whether the noise $\sigma$ is scaled by the layer-wise weight norms, as absolute Gaussian noise $\mathcal{N}(0, \sigma^2 I)$ affects weights with different magnitudes (e.g., embeddings vs. layer norms) disproportionately.
