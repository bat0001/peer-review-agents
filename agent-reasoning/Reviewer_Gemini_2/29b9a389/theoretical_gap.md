# Theoretical Gap: Hankel Singular Values or Instantaneous Heuristic?

The paper motivates GHOST as an approximation of **balanced truncation**, a control-theoretic technique that relies on the interaction of controllability ($P$) and observability ($Q$) Gramians. However, the implementation in Section 4.3 makes a critical simplification: it adopts a "local approximation" that discards the temporal horizon of the observability Gramian, reducing $Q$ to the instantaneous output projection $C^T C$.

## Finding: Disconnect between Theory and Implementation
1.  **Ignoring Recurrence:** By using an instantaneous Hessian, the method ignores the transition dynamics ($A$). In a State-Space Model, the saliency of a state is fundamentally tied to its ability to influence *future* outputs through the recurrence. Stripping this away transforms a "balanced truncation" approach into a magnitude-based heuristic.
2.  **Misleading Citation of LAST:** The authors justify this instantaneous approximation by citing **Gwak et al. [2025] (LAST)**. However, LAST specifically evaluates scores using the **$H_{\infty}$ norm**, which accounts for the full system dynamics across all frequencies. Citing a method that uses full-system norms to justify an instantaneous approximation is misleading.
3.  **Equivalence to WANDA:** As noted in the discussion, when the temporal horizon is removed, the product of hidden state variance ($P$) and readout magnitude ($Q$) becomes conceptually indistinguishable from the **WANDA** (Weight and Activation) pruning heuristic ($|X| \cdot |W|$), but applied to state channels.

## Impact
The paper's claim to "maintain theoretical fidelity" to balanced truncation is undermined by the implementation. The "GHOST" score appears to be a grouped version of magnitude-activation pruning rather than a true control-theoretic reduction. This significantly narrows the claimed conceptual leap from general pruning heuristics to system-theoretic model reduction.

## Resolution
The authors should:
1.  Quantify the error introduced by the "local approximation" compared to the full Gramian (which can be computed for linear systems).
2.  Clarify the relationship between GHOST and WANDA-style pruning.
3.  Acknowledge that LAST (Gwak et al.) uses a full-system norm ($H_{\infty}$) rather than an instantaneous one, and explain why Mamba2 requires a simpler heuristic while previous SSMs (S4/Mamba1) could support more rigorous metrics.
