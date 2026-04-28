# Logic & Reasoning Audit: The Mutual Information Fallacy and Backbone Entanglement in LVRPO

This audit evaluates the formal theoretical claims in Section 3 and Appendix C of the **LVRPO** framework, specifically regarding mutual information maximization and gradient decoupling.

## 1. Finding: The Mutual Information Maximization Fallacy

Theorem 1 (Section C.2) claims that the LVRPO objective maximizes a lower bound on the Mutual Information $I(Z_{und}; Z_{gen})$ between the reasoning hidden states and the generative velocity field. The proof sketch relies on the identity $I(X; Y) = H(X) - H(X|Y)$, arguing that minimizing the conditional entropy $H(Z_{und}|Z_{gen})$ via behavioral rewards directly maximizes $I$.

**Logical Flaw:**
Maximizing $I(X; Y)$ by minimizing $H(X|Y)$ is only valid if the source entropy $H(X)$ is either fixed or bounded from below. In the context of reinforcement learning for preference optimization, it is well-documented that strong reward signals (such as the semantic grounding reward $r_{sem}$) can induce **mode collapse** (reward hacking), where the policy $\pi_\theta$ collapses into a low-entropy state to satisfy the evaluator. 

If the reasoning hidden states $Z_{und}$ collapse to a subset of repetitive, high-reward templates, then the entropy $H(Z_{und})$ **decreases**. In the limit of total mode collapse, $H(Z_{und}) \to 0$, which forces $I(Z_{und}; Z_{gen}) \to 0$, regardless of how perfectly $Z_{gen}$ is conditioned on $Z_{und}$. The manuscript provides no formal lower bound on the entropy of the reasoning state, rendering the claim of Mutual Information *maximization* theoretically unsubstantiated and potentially false in the presence of policy saturation.

## 2. Finding: Vacuous Orthogonality in Proposition 3

Proposition 3 (Section C.3) claims "Modality-Specific Gradient Decoupling," stating that the update direction for the reasoning parameters $\theta_{und}$ is orthogonal to the noise-induced variance of the generative field $\nabla_\theta \mathcal{L}_{gen}$ in the limit of expert specialization.

**Theoretical Inconsistency:**
The "limit of expert specialization" is a vacuous limit for a unified transformer backbone. While the MoT mechanism (Equation 15) provides modality-specific experts (FFNs), the **backbone attention layers are explicitly shared** and jointly optimized (as stated in Line 191). 
- **Attention Entanglement:** The self-attention operation $A_{attn}$ processes the interleaved sequence $(T, V)$ using shared weights $(W_Q, W_K, W_V)$. Any gradient from the generative loss $\mathcal{L}_{gen}$ that updates these shared weights will inherently alter the attention manifold for the reasoning task.
- **Propagation Path:** Modality-specific decoupling is only achieved for the leaf experts, not the structural core of the transformer. Claiming that the update direction for the *reasoning parameters* (which include the shared attention backbone) is orthogonal to generative noise misrepresents the degree of structural coupling in the architecture.

## Recommended Resolution:
1. Revise Theorem 1 to include a formal entropy regularizer or bound that ensures $H(Z_{und})$ is preserved.
2. Narrow the claim of Proposition 3 to specify that decoupling only occurs within the MoE FFN layers, acknowledging the residual entanglement in the shared attention backbone.

**Evidence Source:** Theorem 1, Proposition 3, Equation (15), and Figure 4.
