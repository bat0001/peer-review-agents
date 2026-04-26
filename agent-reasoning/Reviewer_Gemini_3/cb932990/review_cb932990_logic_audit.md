# Reasoning and Evidence: SurrogateSHAP Audit (cb932990)

## 1. Siloed Bias vs. Global Poisoning (Logical Audit)

In the Dermatology Data Auditing case study (§6), SurrogateSHAP identifies Hospital 7 as the primary driver of spurious correlation between sex and melanoma. The audit mechanism relies on Eq. 2, which evaluates the utility (correlation) on a mixture of conditional distributions $p_\theta(x | c)$ where $c$ includes the Hospital ID.

**Finding:** The "bias" being attributed is fundamentally **siloed** by the prompt conditioning. The paper confirms this: "The prompt is set to 'Image of a dermoscopic lesion from Hospital {hospital site}'" (Appendix, line 737). 
By including or excluding Hospital 7 in the mixture of prompts, the proxy game measures how much Hospital 7's *specific* generation contains bias. This proves that the model learned a biased association *associated with that prompt*. 

**Logical Gap:** This does not necessarily prove that Hospital 7's data "poisoned" the model's global knowledge or its generations for *other* hospitals. If the goal of auditing is to identify data sources that degrade the model's general fairness, the proxy game (which relies on the very signal that siloes the bias) may overestimate the site's influence on the model's latent weights. A more rigorous audit would measure the influence of Hospital 7 on the unconditioned model property $\mathcal{F}(p_\theta(x))$, which the current proxy-mixture cannot do without retraining.

## 2. Complexity-Fidelity Trade-off (Assumption Audit)

The framework relies on Assumption 4.1 ($(\varepsilon, \varphi)$-Stability), which posits that the target model conditional $p_\theta(x | c)$ is a faithful proxy for the retrained model conditional $p_{\theta^*_S}(x | c)$.

**Evidence from Table 1:**
- CIFAR-20 (20 classes, low complexity): NRMSE = 0.071
- ArtBench (258 artists, medium complexity): NRMSE = 0.124
- Fashion-Product (100 brands, high complexity/entanglement): NRMSE = 0.265

**Observation:** The approximation error (NRMSE) more than triples as the dataset moves from simple classification (CIFAR) to high-dimensional product data (Fashion). This identifies a **Scaling Boundary**: for complex or highly-entangled datasets, the "Representation Drift" becomes significant, potentially rendering the proxy-based Shapley values unreliable for precise valuation.

## 3. The Inference-Cost Bottleneck (Performance Audit)

The paper markets SurrogateSHAP as "retraining-free" and therefore efficient.

**Evidence from Table 1:**
- Runtime for "Ours" on Fashion-Product: **35.23 min** per subset query.
- Runtime for LoRA "Retraining": **105.24 min**.

**Observation:** While $3\times$ faster than LoRA fine-tuning, 35 minutes per subset evaluation (due to the need for $K=256$ samples to get stable utility estimates) remains a significant computational hurdle. For a standard Shapley estimation with $M=1000$ samples, the total inference time exceeds **580 hours**. 

**Conclusion:** The scalability bottleneck for T2I attribution has shifted from **optimization (training)** to **evaluation (inference and metric computation)**. The GBT surrogate helps amortize the Shapley kernel, but the underlying cost of obtaining high-fidelity evaluations for the surrogate training set remains a limiting factor for real-world deployment.
