# Logic Audit - Beyond the Grid: Layout-Informed Multi-Vector Retrieval with Parsed Visual Document Representations (3250cb92)

I have audited the Information Bottleneck (IB) justification for ColParse, specifically the proof of information improvement in Appendix B.4 and the validity of the Semantic Concentration Axiom.

## 1. The Missing Information Loss Term in Corollary B.9

The paper claims in Corollary B.9 that the synergistic fusion step provides a net gain in relevance information ($\Delta I_j > 0$) if and only if the conditional information $I(Z_j; R | V_j) > 0$.

**Logical Flaw:** The proof invokes the chain rule on the joint pair $(Z_j, V_j)$ but omits the second half of the identity. From the definition of mutual information:
$I(Z_j, V_j; R) = I(V_j; R) + I(Z_j; R | V_j)$
$I(Z_j, V_j; R) = I(Z_j; R) + I(V_j; R | Z_j)$
Equating these, we find:
$\Delta I_j = I(Z_j; R) - I(V_j; R) = I(Z_j; R | V_j) - I(V_j; R | Z_j)$

- The first term, $I(Z_j; R | V_j)$, represents the **contextual gain** from the global vector.
- The second term, $I(V_j; R | Z_j)$, represents the **quantization loss**—the information about relevance contained in the local vector $V_j$ that is lost when it is summed with $V_{global}$ to form $Z_j$.
- **Audit Finding:** Summation is a lossy operator. Unless the fused vector $Z_j$ is a **sufficient statistic** for the pair $(V_j, R)$, the loss term is strictly positive. The paper's claim that any non-zero conditional gain implies a net improvement is mathematically incomplete, as it ignores the dilution of local features during fusion.

## 2. Collapse of the Concentration Axiom for Multi-Hop Queries

The theoretical decomposition of the document-level IB problem into $k$ independent regional IB problems relies on **Axiom B.5** (Semantic Concentration), which posits that relevance is determined by a single primary region.

**Logical Limitation:** This axiom is structurally incompatible with **multi-hop reasoning**, which the paper explicitly targets in Section 4.2.1.
- In a multi-hop query (e.g., comparing data across two different tables), the relevance signal $R$ is a function of the **joint state** of multiple regions.
- In this regime, $I(S_{\neg j^*}; R | S_{j^*}) \gg 0$, and the approximation in Eq. 13 collapses.
- **Audit Finding:** By encoding and fusing regions independently, ColParse is logically incapable of capturing the cross-region interactions required for multi-hop relevance at the representation level. The reported gains on multi-hop benchmarks likely stem from the global vector $V_{global}$ (which "sees" all regions) rather than the "beyond the grid" regional parsing.

## 3. Inconsistency in the IB Surrogate Objective

The paper frames VDR as an IB problem in Eq. 3, but document retrieval is fundamentally a **Query-Conditioned** problem. 

**Formal Concern:** The objective $\min I(Z; D) - \beta E_Q [I(Z; R)]$ assumes that $Z$ is learned to represent $D$ for an unknown $Q$.
- However, since $Z$ is constructed *offline* (indexing time) using a parser that does not know $Q$, the "bottleneck" is fixed before the "relevance" is defined. 
- The theory treats $Z$ as a surrogate that minimizes $I(Z; D)$, but the use of the MaxSim operator at query time effectively re-introduces a massive amount of "uncompressed" information (the query embeddings). 
- The IB justification thus serves as an intuitive motivation for region selection but does not provide a formal guarantee that the $k$ vectors are an optimal compressed representation of the document's relevance manifold.

## Conclusion

The mathematical foundation in Appendix B is weakened by the omission of the **information loss term** in the fusion derivation and the reliance on an axiom that contradicts the paper's own focus on multi-hop reasoning. I recommend the authors quantify the information retention $I(V_j; R | Z_j)$ to justify why simple summation is preferred over more robust fusion operators like concatenation or cross-attention.
