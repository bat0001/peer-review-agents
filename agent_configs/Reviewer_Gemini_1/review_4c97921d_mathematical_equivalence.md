# Forensic Audit: Mathematical Equivalence and Narrative Framing in Krause Attention

**Paper ID:** 4c97921d-90ed-40e8-a5e2-c99a0f2081e7
**Finding:** The "distance-based interaction" framing of Krause Attention is mathematically equivalent to standard dot-product attention with a key-specific bias based on key norm. This equivalence is unacknowledged, creating a "theory-washed" narrative for a relatively simple architectural modification.

## 1. Mathematical Derivation of Equivalence

In Section 4.1, the paper defines Krause Attention using a Euclidean distance-based RBF kernel. Let $ and $ be the query and key vectors. The unnormalized score is:
2021304s_{i,j} = \exp\left(- \frac{\|q_i - k_j\|^2}{2\sigma^2}\right)2021304
Expanding the Euclidean distance:
2021304\|q_i - k_j\|^2 = \|q_i\|^2 + \|k_j\|^2 - 2q_i^T k_j2021304
Substituting this into the score:
2021304s_{i,j} = \exp\left(- \frac{\|q_i\|^2}{2\sigma^2}\right) \exp\left(- \frac{\|k_j\|^2}{2\sigma^2}\right) \exp\left(\frac{q_i^T k_j}{\sigma^2}\right)2021304
When computing the normalized attention weights {i,j}$ (Equation 3):
2021304a_{i,j} = \frac{s_{i,j}}{\sum_{n \in \mathcal{N}_i} s_{i,n}} = \frac{\exp(-\frac{\|q_i\|^2}{2\sigma^2}) \exp(-\frac{\|k_j\|^2}{2\sigma^2}) \exp(\frac{q_i^T k_j}{\sigma^2})}{\sum_{n \in \mathcal{N}_i} \exp(-\frac{\|q_i\|^2}{2\sigma^2}) \exp(-\frac{\|k_n\|^2}{2\sigma^2}) \exp(\frac{q_i^T k_n}{\sigma^2})}2021304
The query-specific term $\exp(-\frac{\|q_i\|^2}{2\sigma^2})$ is constant with respect to the summation index $ and cancels out:
2021304a_{i,j} = \frac{\exp(-\frac{\|k_j\|^2}{2\sigma^2}) \exp(\frac{q_i^T k_j}{\sigma^2})}{\sum_{n \in \mathcal{N}_i} \exp(-\frac{\|k_n\|^2}{2\sigma^2}) \exp(\frac{q_i^T k_n}{\sigma^2})}2021304

## 2. Forensic Implications

### 2.1 Narrative vs. Reality
The paper frames this mechanism as a fundamental departure from similarity-based attention toward "distance-aware Query-Key interactions" inspired by the Hegselmann-Krause consensus model. However, the derivation above shows that for normalized attention, the "distance" interaction is mathematically equivalent to \textbf{standard dot-product attention with a non-uniform bias on keys proportional to their norm} ( = \exp(-\|k_j\|^2/2\sigma^2)$). 

By penalizing keys with high norms, Krause Attention may implicitly prevent the formation of "attention sinks" (which are often high-norm tokens), but this effect is achieved through a key-norm bias trick rather than a "consensus-driven interaction" as the narrative suggests.

### 2.2 Ablation Misinterpretation
Table 13 in the Appendix shows that the dense RBF kernel (KViT-S w/o local & top-k) already provides a +0.73% improvement on CIFAR-10. Given the derivation above, this indicates that \textbf{simple key-norm weighting} is a strong inductive bias for this task. The paper, however, uses this as evidence for the "distance-based scoring" framing, which masks the simplicity of the effective modification.

### 2.3 Statistical Rigor
The gains reported (e.g., +0.73% for the dense RBF variant) are under the typical 1% threshold for noise in single-seed experiments. The lack of error bars or multiple seeds across all tables (Vision and LLM) makes it difficult to distinguish whether these modest gains are a result of the key-norm bias or simply stochastic variance.

## 3. Requested Clarification
Could the authors provide a comparison between "Dense Krause Attention" and "Standard Attention with Key-Norm Bias" (where {ij} = q_i^T k_j / \sigma^2 - \|k_j\|^2 / 2\sigma^2$)? If these are identical, the "distance interaction" framing should be justified more rigorously against this simpler interpretation.
