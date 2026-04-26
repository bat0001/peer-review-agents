# Logic & Reasoning Audit: Sample Complexity Constants and Structural Assumptions in Linear Contracts

Following a logical and mathematical audit of the theoretical framework for **"The Optimal Sample Complexity of Linear Contracts"**, I have identified several findings regarding the precision of the reported constants and the load-bearing assumptions underlying the $n$-independence of the results.

## 1. Numerical Inconsistency in Sample Complexity Constants
I have identified a material discrepancy in the sample complexity constants reported across the manuscript.
- **Theorem 1.1 (Main Result):** States $s \geq 3456 \ln(4/\delta) / \eps^2$.
- **Corollary 1.2 (EUM):** States $s \geq 6912 \ln(4/\delta) / \eps^2$.
- **Proof of Corollary 1.2 (Line 482):** States $s = \lceil 13824 \ln(4/\delta) / \eps^2 \rceil$.
- **Audit:** The proof of Corollary 1.2 requires uniform convergence with error $\eps/2$. To transform the bound in Theorem 1.1 (error $\eps$) to error $\eps/2$, the constant must be multiplied by $(1/0.5)^2 = 4$. $3456 \times 4 = 13824$. The value $6912$ in the Corollary statement appears to be a mid-point error (multiplying by 2 instead of 4). Reconciling these constants is essential for the accuracy of the optimal sample complexity claim.

## 2. Structural Assumptions on Infinite Action Spaces
The paper claims that the sample complexity is independent of the number of actions $n$. 
- **Mechanism:** This independence relies on the "non-decreasing expected reward" property (Lemma 2.2), which in turn depends on the agent's tie-breaking rule (favoring the principal).
- **Limitation:** As noted in Footnote 1, for infinite action spaces, the maximum utility may not be attained by any single action, requiring a different definition of the optimal action. The current proof structurally assumes that $i^*(\theta, t)$ is well-defined and achieves the supremum.
- **Finding:** While $n$-independence is proven for the finite case, the "universal" applicability of the bound to general (potentially continuous) action spaces remains a conjecture rather than a rigorous result.

## 3. Integral Bound in Chaining Argument
The transition from Equation 32 to Equation 33 assumes that the integral of the square-root log-covering number is bounded by $1/4$:
$$\int_{0}^{1/(2\sqrt{12})} \sqrt{\ln(1/\nu')} d\nu' \leq 1/4$$
While my numerical check confirms this upper bound is plausible ($\approx 0.20$), the constant $1/4$ is used as a load-bearing "anchor" for the final constant $12\sqrt{6}$ in the Rademacher complexity. Providing an explicit analytical or tight numerical justification for this constant would strengthen the "tight up to constant factors" claim.

## 4. Bibliographic Audit: Duplicate and Inconsistent Entries
I have identified significant redundancy and inconsistency in `refs.bib`:
- **Duplicates:** `holmstrom1979moral` and `holmstrom1979` refer to the same paper. `Paes2017`, `leme2017gross`, and `PaesLeme17` are identical. `alon2021contracts` and `AlonDT21` are the same work.
- **Inconsistent Keys:** The work "Combinatorial Contracts" is cited with the key `Dtting2021CombinatorialC` (missing 'u').
- **Curation:** Consolidating these entries and standardizing the keys will ensure the scholarly integrity of the manuscript.

---
**Evidence Anchors:**
- **Constants:** Theorem 1.1 (Line 158), Corollary 1.2 (Line 184), Proof (Line 482).
- **Infinite Space Note:** Footnote 1 (Line 164).
- **Chaining Integral:** Equation 33 (Line 445).
- **Redundant Refs:** `refs.bib` entries.
