# Reasoning for Theory-Experiment Gap (Looped TF) - Paper d2b67d3c

## Finding
There is a significant structural gap between the "Inductive Bias" theory presented in Section 2.1 and the experiments in Section 3.1. The theory explains OOD gains via group-theoretic constraints (gcd conditions) on a specific "cycle task," while the experiments use a "p-hop" backtracking task with a parity-based ID/OOD split.

## Evidence
1. **Task Mismatch:** Theorem 2.1 analyzes a cyclic permutation \(z\) on \(n\) points. The experiment (Section 3.1) uses a 4-hop backtracking task on an alphabet of size 4. These are qualitatively different functional structures.
2. **Exponent Logic:** The theory relies on the property that \(k\)-fold iterates of a cycle \(z\) are unique if \(\gcd(k, n)=1\) and \(\gcd(k, n-1)>1\). This logic is tied to the algebraic properties of permutations. It is not shown (or even intuited) how this applies to the $p$-hop task, which involves conditional branching (backtracking) rather than a simple cycle.
3. **ID/OOD Split Mismatch:** In the theory, the ID/OOD split is a single held-out point. In the experiment, the split is based on the parity of the sum of jump indices (\(\sum i_t\) even vs. odd). The theory does not explain why self-iteration would favor a "parity-agnostic" solution over a "parity-aware" shortcut.
4. **Architectural Gap:** The theory assumes an unconstrained base class \(\gF_1\) (Theorem 2.1). The experiment uses a Transformer block with LayerNorm and GELU, which introduces its own architectural inductive biases that are not accounted for in the "iterated unconstrained class" model.

## Recommendation
The authors should clarify the connection between the cycle task theory and the $p$-hop experiments. Specifically, they should explain whether they believe the "gcd-based uniqueness" mechanism is active in the $p$-hop setting, or if there is a different mechanistic reason (e.g., related to the parity-based split) why self-iteration improves OOD performance there.
