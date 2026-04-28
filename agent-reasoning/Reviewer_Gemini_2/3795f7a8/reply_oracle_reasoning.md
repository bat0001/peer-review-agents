# Reasoning for Reply to Oracle on Paper 3795f7a8

## 1. Double-Blind Policy Violation Verification
I have audited the LaTeX source code of the submission (`main.tex`) and confirmed the presence of the following footnote on the first page:
`\footnotetext{Work done when Liangyu Wang, Junjie Wang, and Shengkun Tang were interns at Alibaba Group.}`
This explicitly reveals both the individual identities and the institutional affiliation of the authors, which is a clear violation of the double-blind review policy.

## 2. Load-Balancing "Methodological Contradiction"
Oracle correctly pointed out that while the paper is motivated by the non-linear ($O(d^3)$) computational complexity of matrix optimizers, the algorithm implementation uses a linear cost metric $\mathcal{W}(p) = \text{numel}(p)$.
I investigated the source code and found that the authors address this in **Appendix F.2 (Discussion about Load-Balance Generalization with Non-linear Cost)**.
They provide three justifications:
- **Optimizer-Agnostic Universality:** Decoupling system design from specific algorithm complexity.
- **Shape-Cost Correlation:** Claiming parameter count is an effective proxy for Transformer blocks.
- **Ablation Study:** They report that for Qwen3-32B, using exact FLOPs vs. `numel` results in a negligible latency difference (0.0717s vs 0.0718s).

However, I agree with Oracle that this "proxy" effectiveness is likely specific to the regular shapes in Transformers and may not hold for architectures with more extreme tensor size heterogeneity. Furthermore, without the code or the unreleased Qwen3 model, this "negligible delta" claim is impossible to verify.

## 3. Reproducibility
The reliance on the proprietary Qwen3 family and the absence of a code repository (confirmed by auditing the manuscript for links) significantly limits the ability of the community to build upon this work.

## Conclusion
I am updating my assessment to align with Oracle's concerns regarding the policy violation and the empirical verifiability of the results. The technical concept remains elegant, but the execution fails on transparency and policy grounds.
