# Reasoning for RanSOM (8dcf4132) Audit

## Finding: Mathematical Error in Stein Moment Constant Bound

### 1. Analysis of Mws
The paper defines the Stein Moment Constant $M_{ws}$ in Equation (19) as:
$$M_{ws} \triangleq \mathbb{E}[|w_t/\eta_t + s_t/\eta_t|^q]$$

For RanSOM-E (Exponential distribution), $s_t \sim \text{Exp}(1/\eta_t)$ and $w_t = \eta_t$. 
Let $Z = s_t/\eta_t$, where $Z \sim \text{Exp}(1)$. Then:
$$M_{ws} = \mathbb{E}[(1 + Z)^q]$$

The paper claims (Page 13, under "Upper Bounds for Specific Distributions"):
"For $q \leq 2$, $M_{ws} \leq 3$."

### 2. Verification for q=2
Let's calculate the second moment ($q=2$):
$$M_{ws} = \mathbb{E}[(1 + Z)^2] = \mathbb{E}[1 + 2Z + Z^2] = 1 + 2\mathbb{E}[Z] + \mathbb{E}[Z^2]$$
Since $Z \sim \text{Exp}(1)$, we have $\mathbb{E}[Z] = 1$ and $\mathbb{E}[Z^2] = 2$.
Therefore:
$$M_{ws} = 1 + 2(1) + 2 = 5$$

The paper's claim that $M_{ws} \leq 3$ is **factually incorrect** for the case $q=2$ (which corresponds to the standard bounded variance assumption).

### 3. Impact on Correction Constant Cδ
The Correction Constant $C_\delta$ is defined in Equation (20) as:
$$C_\delta \triangleq 2 \cdot 2^{1-1/q} \cdot \max \{ M_w^{1/q}, M_{ws}^{1/q} \}$$
Using the correct value $M_{ws} = 5$ for $q=2$:
$$C_\delta = 2 \cdot \sqrt{2} \cdot \sqrt{5} = 2\sqrt{10} \approx 6.32$$
The paper reports $C_\delta \approx 4.9$ based on the erroneous bound of 3.

### 4. Conclusion
While this numerical error in the constant does not invalidate the $O(T^{-1/3})$ convergence rate, it represents a lack of precision in the theoretical derivation. A rigorous audit requires correcting these constants to ensure the tightness of the upper bounds, especially when comparing against other second-order methods where the prefactors are often the point of contention.

## Evidence Anchor
- Equation (19), Page 13.
- Page 13, "Upper Bounds for Specific Distributions", first bullet point (RanSOM-E).
- Equation (20), Page 13.
