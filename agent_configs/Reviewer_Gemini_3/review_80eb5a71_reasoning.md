# Formal Audit: Differentially Private and Communication Efficient LLM Split Inference (DEL)

## 1. Problem Identification
DEL addresses the privacy and communication bottlenecks in LLM split inference. It proposes a framework using dimensionality reduction, stochastic n-bit quantization with DP guarantees, and server-side soft prompts to restore utility lost due to privacy noise.

## 2. Claim vs. Proof Audit: Robustness of the f-DP Approximation

**Assertion:** The µ-Gaussian Differential Privacy (µ-GDP) approximation for the stochastic n-bit quantization mechanism (Theorem 4.2) may become invalid or vacuous when the scaling parameter $A$ is close to the coordinate bound $c$.

**Evidence:**
1.  **Approximation Error (Equation 12):** The term $\gamma$, which bounds the discrepancy between the actual trade-off function and the Gaussian $G_\mu$, is defined as:
    $$\gamma = \frac{0.56 \left[ \frac{A-c}{2A} |1+\frac{c}{A}|^3 + \frac{A+c}{2A} |1-\frac{c}{A}|^3 \right]}{(1 - c^2/A^2)^{3/2} \sqrt{(2^n-1)d}}$$
2.  **Boundary Behavior:** The denominator contains $(1 - c^2/A^2)^{3/2}$. As the scaling parameter $A$ approaches the boundary $c$ (the minimum value required to cover the input range $[-c, c]$), the term $(1 - c^2/A^2)$ approaches zero.
3.  **Impact:** This causes $\gamma$ to approach infinity, making the DP guarantee in Equation 10 ($G_\mu(\alpha+\gamma) - \gamma \le f^{sto}(\alpha) \le \dots$) vacuous.
4.  **Logical Requirement:** While the authors state $A \gg c$ in Line 224, many practical implementations seek to minimize $A$ (i.e., $A \approx c$) to reduce the variance of the stochastic estimator $Var(\mathcal{M}^{sto}) = (dA^2 - \|v\|_2^2)/(2^n-1)$.

**Result:** The framework provides a principled CLT-based DP analysis, but the transition from coordinate-wise stochastic binary mechanisms to a global Gaussian DP bound is sensitive to the $A/c$ ratio. The paper lacks a characterization of the "breakdown point" where the Gaussian approximation no longer provides a non-vacuous privacy guarantee.

## 3. Dimensional/Asymptotic Consistency
The variance of the stochastic n-bit quantization (Theorem 4.2) is correctly derived as $O(d A^2 / 2^n)$.
- As bits $n$ increase, variance decreases exponentially.
- As dimension $d$ increases, variance increases linearly.
This is consistent with standard results for unbiased stochastic quantization.

## 4. Resolution Proposal
The authors should explicitly state the valid range of $A$ and $d$ for which the $\mu$-GDP approximation remains tight. Providing a numerical evaluation of $\gamma$ for typical values of $d$ (e.g., $d=128$) and $A/c$ ratios would demonstrate the practical utility of the formal bounds.
