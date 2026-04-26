# Logic & Reasoning Audit - SymPlex (3ea0c667)

## Finding 1: Formal Vocabulary-Result Inconsistency

**Evidence:**
- **Definition (Section 3.2, Page 3):** The vocabulary is defined as $\mathcal{V} = \mathcal{B} \cup \mathcal{U} \cup \mathcal{T}$. Binary operators $\mathcal{B}$ are restricted to $\{+, -, \times, /\}$. 
- **Definition (Appendix A.1, Page 11):** Explicitly lists binary operators as `+, -, *, /`.
- **Results (Table 4, Page 8):** Reports predicted solutions such as `((y)^4 * 1.2) - (-x^4)` for the Poisson equation and `(x - t)^2` for the Advection equation.
- **Results (Section E.1, Page 22):** Shows SymPlex outputs like `((y )^4 * 1.2) - (-x^4)`.

**Logical Gap:**
The paper emphasizes "grammar-constrained autoregressive decoding" (Section 4.3) and "syntactic validity through grammar-constrained decoding" (Abstract) as core mechanisms to ensure only well-formed expressions are generated from the vocabulary $\mathcal{V}$. If the caret operator `^` (exponentiation) is not in the defined set of binary operators $\mathcal{B}$, it should be unreachable by the policy. The presence of `^` in the results suggests either:
1. The formal definitions in Section 3.2 and A.1 are incomplete/incorrect.
2. The implementation used a different vocabulary than the one described.
3. The results were post-processed into a format using `^` that does not reflect the raw output of the tree-structured Transformer.

## Finding 2: Vocabulary Leakage of Parametric Variables

**Evidence:**
- **Curriculum Design (Section 5.4, Page 15):** Stage 2 (Spatiotemporal dynamics) vocabulary $\mathcal{V}_{Stage2}$ is defined as $\mathcal{B} \cup \mathcal{U} \cup \{x_1, \dots, x_n, t, const\}$, explicitly excluding the parameter $\kappa$.
- **Results (Table 4, Page 8):** The "Predict Solution" for the **Heat** equation (a Smooth Problem, not the Parametric version) is given as `(sin(x) * (exp((-2.0*(k * t))) * (0.99 * cos(y))))`.

**Logical Gap:**
The symbol `k` corresponds to the physical parameter $\kappa$ (defined in Section 3.1). According to the curriculum, non-parametric problems like the Smooth Heat equation are solved in Stage 2, where `k` is not part of the allowed vocabulary. The appearance of `k` in the reported solution for a non-parametric task indicates a violation of the "grammar-constrained" and "stage-specific vocabulary" claims. If the model was able to select `k`, it implies the vocabulary constraints were not enforced as described, or the model was trained with the parametric vocabulary even for non-parametric tasks.

## Finding 3: Definitional Circularity in Symbolic Recovery Guarantees

**Evidence:**
- **Theorem 5.1(i) (Page 6):** "If $\pi_\theta$ is globally optimal, there exists a tree $T^*$ in its support... such that $u_{T^*} = u^*$."
- **Proof (Appendix D.3, Page 20):** Relies on Assumption (A2) (existence of $T^*$) and (A4) (uniqueness of zero residual).

**Logical Gap:**
As noted in the discussion, this theorem is a tautology derived from the definition of "global optimality" in an RL context. If a unique reward-maximizing state $T^*$ exists (Assumptions A2 and A4), any policy that maximizes the expected reward $J(\pi)$ must, by definition, assign probability to that state. The theorem provides no insight into the **attainability** of this global optimum via the SymFormer architecture or the SymPlex RL framework. It establishes representational sufficiency (which is trivial for a finite tree space) rather than convergence or discovery reliability.

## Conclusion
The discrepancies between the formal definitions of the symbolic grammar and the reported empirical results suggest a lack of internal consistency in the paper's documentation of its implementation. Furthermore, the inclusion of parametric variables in non-parametric solution outputs raises questions about the rigor of the curriculum-based vocabulary constraints. These issues, combined with the definitional nature of the theoretical guarantees, weaken the claim of a "principled framework" for symbolic discovery.
