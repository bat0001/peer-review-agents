# Reasoning: The Heuristic-Preserving Nature of GauS Optimization

This file documents the formal logical derivation showing that GauS, under its proposed initialization, acts as a "Heuristic-Preserving Resource Shifter" rather than a global optimizer.

## 1. The Initialization Lock
The paper proposes:
$$\sigma_i = \kappa \cdot (s_i^{ALAP} - s_i^{ASAP})$$
For any node $i$ on the critical path, $s_i^{ALAP} = s_i^{ASAP}$ by definition. Thus, $\sigma_i = 0$ at $t=0$.

## 2. Gradient Collapse on the Critical Path
The gradient of the probability mass w.r.t. the mean $\mu_i$ for a Dirac delta distribution ($\sigma=0$) is zero everywhere except at the rounding boundary. 
Since $\mu_i$ is initialized at the integer midpoint (ASAP=ALAP), it is far from the boundaries ($d \pm 0.5$).
Thus, $\frac{\partial P_i^d}{\partial \mu_i} = 0$.

## 3. Preservation of Heuristic Latency
The global latency $L$ of a schedule is determined by the length of the critical path. If all nodes on the critical path are frozen (zero gradient), the optimizer cannot change their scheduled steps.
Consequently, the final latency $L_{GauS}$ must be identically equal to the heuristic latency $L_{heuristic}$ used for initialization (ASAP/ALAP).

## 4. Conclusion: Optimization vs. Shifting
GauS only optimizes the placement of nodes with "freedom" (non-critical nodes) to satisfy resource constraints. While this is useful for resource-constrained scheduling, it logically cannot improve the **latency** of the schedule beyond the initial heuristic. 
The "improvement" reported in Section 4.1 likely reflects better resource-satisfaction for a *fixed* latency, or the ability to find *any* feasible schedule where the cold-started stochastic baseline (GS-Schedule) fails to converge. The claim of "Pareto-optimality" is thus limited to the resource axis, as the latency axis is heuristically fixed.
