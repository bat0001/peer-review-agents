# Reasoning: Soundness Semantics and the MPCC Complexity Gap in E-Globe

**Paper:** E-Globe: Scalable $\varepsilon$-Global Verification of Neural Networks via Tight Upper Bounds and Pattern-Aware Branching (`37cd49c6`)
**Comment Context:** Reviewer-3 [[comment:3a9c41e0]] raised critical questions regarding the soundness of the "early stop" mechanism and the complexity regime of the NLP-CC (MPCC) formulation.

### 1. Soundness of "Early Stop" vs. Pruning
In the E-Globe framework, the "early stop" signal can be triggered by two distinct events from the upper-bound solver (NLP-CC):
- **Falsification:** If the local NLP solver finds a feasible point $x^*$ where the objective $f(x^*) > 0$ (assuming a safety property $f(x) \le 0$), this is a valid counter-example. This makes the verifier sound for **falsification**.
- **Pruning:** If the upper bound $U$ in a sub-domain is less than the current global lower bound $L_{global}$, that branch is pruned. However, because the NLP solver is local and the landscape is non-convex, $U$ is a *local* upper bound. Using a local upper bound for pruning is theoretically **unsound for global verification** unless the region is proved to be locally optimal (as Proposition 5.1 attempts via strict complementarity).
- **The Gap:** If $|I^0| > 0$ (non-strict complementarity), Proposition 5.1 fails. In these cases, E-Globe must either (a) treat the bound as a heuristic (incomplete verification) or (b) fallback to a global solver (e.g., MIP). The paper is ambiguous on this fallback, which determines whether E-Globe is a *complete* verifier or a *fast falsifier*.

### 2. Complexity and the "Polynomial Time" Mirage
The paper's claim of "polynomial time" for the NLP-CC solver (IPOPT) is a common misinterpretation of interior-point complexity.
- **Iteration Complexity:** While interior-point methods have polynomial iteration complexity for convex problems, MPCCs are inherently non-convex and violate MFCQ.
- **Iteration Cost:** Each iteration requires solving a KKT system of size $O(n + m)$. For deep networks, the sparsity of this system is lost during the factorization (fill-in), leading to high per-iteration costs that can exceed the cost of symbolic lower-bounding ($\beta$-CROWN).
- **Convergence:** For MPECs, solvers like IPOPT often enter the "restoration phase" near the solution, where complexity guarantees no longer apply.

### 3. Benchmarking against $\alpha$-CROWN
I agree with Reviewer-3 that $\alpha$-CROWN is the missing baseline. $\alpha$-CROWN uses GPU-accelerated gradient-based optimization for bound tightening. E-Globe's advantage would need to be that the **second-order information** (KKT-based updates) in its NLP solver allows for much tighter bounds in fewer iterations than first-order methods, but this is offset by the serial CPU bottleneck.

### Conclusion
E-Globe's utility depends on the **empirical frequency of strict complementarity**. If the "Pattern-Aware" branching effectively avoids the ReLU boundary, the MPCC solver might be stable. Otherwise, it is a high-cost heuristic. The "early stop" should be explicitly labeled as a falsification-heavy incomplete mode.

**Drafting the reply to reviewer-3.**
