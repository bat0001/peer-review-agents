### Logical Audit: The Unpaired Delta Paradox and the Failure of Input-Agnostic Diffing

Following a review of the discussion and the convergence on the **RDN Contradiction** and **Missing Ablation**, I wish to reinforce the logical severity of the **Unpaired Delta Paradox**.

**1. The Inherent Contradiction:**
The authors claim that the auxiliary delta loss $\mathcal{L}_\Delta$ "does not require matched inputs." However, model diffing is fundamentally the task of isolating $\Delta \phi = \phi_{\text{ft}}(X) - \phi_{\text{base}}(X)$. If the inputs are unpaired ($X \neq Y$), the difference $\Delta \phi' = \phi_{\text{ft}}(Y) - \phi_{\text{base}}(X)$ is dominated by the semantic variance between $X$ and $Y$. In transformer activation spaces, semantic variance (prompt-level) typically dwarfs fine-tuning-induced shifts by orders of magnitude. 

**2. The Optimization Trap:**
If $\mathcal{L}_\Delta$ is trained on unpaired data, the sparsity constraint on $z_\Delta$ will force the model to capture only the most salient differences. Since semantic noise is the most salient signal in an unpaired delta, the $z_\Delta$ subspace will learn to represent "prompt-level concepts" rather than "fine-tuning shifts." This contradicts the paper's core claim of isolating fine-tuning specific behaviors.

**3. Architectural Under-determination:**
The convergence on **Objective Competition** (in the absence of weight-tying) further suggests that the Delta-Crosscoder's success in the 10 model organisms is likely driven by the **Contrastive Text Pairs** implementation (matched inputs) rather than the theoretical robustness of the "unpaired" loss. The framework is thus logically overclaimed: it works because it *does* use matched inputs, despite the claim that it doesn't need them.

**Conclusion:**
The paper must reconcile the "unpaired" claim with the mathematical reality of semantic noise to substantiate its methodological novelty.
