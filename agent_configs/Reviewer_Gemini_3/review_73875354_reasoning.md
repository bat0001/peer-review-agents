# Formal Audit: GauS: Differentiable Scheduling Optimization via Gaussian Reparameterization

## 1. Problem Identification
The paper addresses the scalability and ordinal-blindness issues of categorical differentiable scheduling by modeling operator start times as continuous Gaussian random variables, enabling gradient-based optimization in a reduced parameter space.

## 2. Claim vs. Proof Audit

### 2.1 Off-by-one Error in Expected Dependency Violations (Equation 8b)
**Assertion:** The expected dependency violation count $V_{Dep}$ in Equation 8b is systematically under-calculated.

**Evidence:**
Equation 1 defines the dependency constraint as:
$$s_i + Lat(v_i) \le s_j$$
The authors assume $Lat(v_i) = 1$ for simplicity, which reduces the constraint to $s_i < s_j$ for discrete steps $s_i, s_j \in \mathbb{N}$.
A violation occurs if $s_j \le s_i$.

Equation 8b defines the expected violations as:
$$\widehat{V}_{Dep} = \sum_{(v_i, v_j) \in E} \sum_{d_i=1}^{D-1} \sum_{d_j=0}^{d_i-1} P_i^{d_i} \cdot P_j^{d_j}$$

**Counter-example:**
Consider a producer $v_i$ and consumer $v_j$. If the relaxation places them both in the same step $d=k$ with high probability (i.e., $P_i^k \approx 1$ and $P_j^k \approx 1$), this is a violation of the $s_i < s_j$ constraint.
However, Equation 8b only sums over $d_j < d_i$. When $d_i = k$, the inner sum ends at $k-1$. Thus, the case where $d_j = d_i$ is completely ignored.
Furthermore, if $d_i = 0$, the constraint is $0 + 1 \le s_j \implies s_j \ge 1$. A violation occurs if $s_j = 0$.
In Equation 8b, the sum for $d_i$ starts at 1, so violations where the producer is at step 0 are entirely omitted.

**Result:** The objective function under-penalizes "illegal" overlaps and same-step placements, leading to a loose relaxation that may struggle to find strictly feasible schedules without heavy reliance on the "legalization" heuristic.

### 2.2 Off-by-one Error in Expected Recurrence Violations (Equation 24)
**Assertion:** Equation 24 for modulo scheduling recurrence violations contains a similar off-by-one error.

**Evidence:**
Constraint (Eq 6): $s_i + k \cdot II \ge s_j + Lat(v_j)$.
With $Lat(v_j)=1$: $s_j \le s_i + k \cdot II - 1$.
Violation if $s_j \ge s_i + k \cdot II$.

Equation 24:
$$\widehat{V}_{Rec} = \sum_{(v_i, v_j, k) \in E_B} \sum_{d_i=1}^{D-1} \sum_{d_j=d_i + k \cdot II + 1}^{D-1} P_i^{d_i} \cdot P_j^{d_j}$$
The inner summation starts at $d_j = d_i + k \cdot II + 1$, thus omitting the violation case $d_j = d_i + k \cdot II$.

## 3. Hidden Issue: The "Vanishing Peak" Gap (Equation 10b)
The paper approximates the peak resource usage using LogSumExp over the *expected* usages per step:
$$L_{Reg} \approx \tau \cdot \log (\sum_d \exp(\frac{E[Reg(d)]}{\tau}))$$
However, the true objective is the expectation of the peak: $E[\max_d Usage(d)]$.
By Jensen's inequality or simple observation of variance, $\max_d E[Usage(d)] \le E[\max_d Usage(d)]$.
When the uncertainty $\sigma$ is large, the expectation $E[Reg(d)]$ "blurs" the resource demand across the entire timeline, significantly lowering the apparent peak. A realization (sample) might have 10 operators colliding in one step, while the expectation shows each step having a usage of $\approx 1$.
This means the optimizer receives no signal to reduce peak usage until $\sigma$ is already small, defeating the purpose of the continuous relaxation for peak-load balancing.

## 4. Resolution Proposal
1. Correct the summation limits in Equations 8b and 24 to include the boundary cases ($d_j \le d_i$ for dependency and $d_j \ge d_i + k \cdot II$ for recurrence).
2. For the resource peak, consider a variance-aware proxy or a heavier penalty on steps where $E[Usage(d)]$ is high, rather than relying solely on the LSE of expectations.
