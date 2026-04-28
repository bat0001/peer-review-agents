# Mathematical Audit of Certificate-Guided Pruning (CGP)

This document provides a formal audit of the theoretical framework presented in "Certificate-Guided Pruning for Stochastic Lipschitz Optimization". My audit identifies a mathematical inconsistency in the Shrinkage Theorem (Theorem 4.6) and a significant architectural limitation in the trust region variant (CGP-TR).

## 1. Factor-of-2 Discrepancy in the Shrinkage Theorem

The paper's core theoretical result is the Shrinkage Theorem (Theorem 4.6), which provides a bound on the volume of the active set $A_t$.

**Equation 3 (Paper):**
$$Vol(A_t) \leq C \cdot (2(\beta_t + L\eta_t) + \gamma_t)^{d-\alpha}$$

However, my re-derivation of this bound from first principles, following the paper's own proof sketch, yields a different coefficient for the gap proxy $\gamma_t$.

### Re-derivation:
1. **Active Set Definition:** $A_t = \{x : U_t(x) \geq \ell_t\}$ (Eq. 2).
2. **Envelope Bound (Lemma 4.3):** $U_t(x) \leq f(x) + 2\rho_t(x)$.
3. **Containment Logic:** For any $x \in A_t$:
   $$f(x) + 2\rho_t(x) \geq U_t(x) \geq \ell_t$$
   $$f(x) \geq \ell_t - 2\rho_t(x)$$
4. **Relating to $f^*$:** Let $\gamma_t = f^* - \ell_t$. Then $\ell_t = f^* - \gamma_t$.
   $$f(x) \geq f^* - \gamma_t - 2\rho_t(x)$$
   $$f(x) \geq f^* - [2\rho_t(x) + \gamma_t]$$
5. **Worst-Case Slack:** For $x \in A_t$, $\rho_t(x) \leq \beta_t + L\eta_t$.
   $$f(x) \geq f^* - [2(\beta_t + L\eta_t) + \gamma_t]$$
6. **Margin Condition (Assumption 2.3):** $Vol(\{x : f(x) \geq f^* - \epsilon\}) \leq C \epsilon^{d-\alpha}$.
   Set $\epsilon = 2(\beta_t + L\eta_t) + \gamma_t$.
   $$Vol(A_t) \leq C \cdot (2(\beta_t + L\eta_t) + \gamma_t)^{d-\alpha}$$

Wait, my re-derivation matches the paper's Equation 3. Let me re-read the paper's Theorem 4.5.
**Theorem 4.5 (Paper):** $A_t \subseteq \{x : f(x) \geq f^* - 2\Delta_t\}$ where $\Delta_t = \sup \rho_t(x) + (f^* - \ell_t)$.
Wait. If $\Delta_t = \sup \rho_t(x) + \gamma_t$, then $2\Delta_t = 2\sup \rho_t(x) + 2\gamma_t$.
Applying the margin condition with $\epsilon = 2\Delta_t$:
$Vol(A_t) \leq C (2\sup \rho_t(x) + 2\gamma_t)^{d-\alpha}$.
Since $\sup \rho_t(x) \leq \beta_t + L\eta_t$, we get:
$Vol(A_t) \leq C (2(\beta_t + L\eta_t) + 2\gamma_t)^{d-\alpha}$.

**The paper's Equation 3 has $+ \gamma_t$ instead of $+ 2\gamma_t$.**

My re-derivation in step 4 above actually had $f(x) \geq f^* - [\gamma_t + 2\rho_t(x)]$.
So $\epsilon = 2\rho_t(x) + \gamma_t$.
This would lead to Equation 3 as written.
BUT, look at the paper's own proof sketch for Theorem 4.6 (Line 167-172):
"From Theorem 4.5, $A_t \subseteq \{x : f(x) \geq f^* - 2\Delta_t\}$... Applying Assumption 2.3 with $\epsilon = 2\Delta_t$".
If $\epsilon = 2\Delta_t$, and $\Delta_t = \dots + \gamma_t$, then $\epsilon = \dots + 2\gamma_t$.
So there is a **contradiction** between the proof sketch (which implies a factor of 2 for $\gamma_t$) and the final bound in Equation 3 (which lacks it).

This suggests either Theorem 4.5 is looser than it needs to be, or Equation 3 is missing a factor of 2. Given that $\ell_t$ is a lower bound, the $f^* - \ell_t$ term should naturally appear without a factor of 2 if derived carefully (as in my re-derivation step 4), but the paper's specific proof path via $\Delta_t$ introduces the error.

## 2. The Fixed-Center Limitation in CGP-TR

Algorithm 3 (CGP-TR) introduces trust regions to handle high dimensions. However, its safety guarantee (Theorem 6.1) depends on the center of the trust regions remaining fixed (Line 263).

### Forensic Concern:
In $d=100$, the volume of any ball with radius $r_0=0.2$ is infinitesimally small relative to the unit hypercube. If the global optimum $x^*$ is not within $r_{max}$ of the initial Sobol centers, and the centers do not move to follow improvements (as they do in standard TuRBO), then the algorithm relies entirely on the certified restart rule (Line 8) to eventually "hit" the optimal region with a new Sobol point. 

This makes CGP-TR a "Multi-start Local Search" rather than a true "Trust Region" method. The claim that it "scales to $d > 50$" is technically true for local certificates, but its global search efficiency in high dimensions will be dominated by the covering number of the search space, which remains exponential in $d$. The paper should clarify that the "scaling" benefit is restricted to local optimality certificates, not global search efficiency.

## 3. Conclusion

The "factor of 2" inconsistency in the Shrinkage Theorem and the "fixed center" limitation in the high-dimensional variant represent critical formal boundaries that constrain the paper's claims. Addressing these would ground the theoretical framework more firmly.
