# Forensic Analysis: Sensitivity to Registration Accuracy and Theoretical-Empirical Gap

## Overview
This document provides the forensic evidence supporting the finding that Transport Clustering (TC) is highly sensitive to the accuracy of the full-rank registration map, and that its provided theoretical guarantees do not currently account for the approximate solvers required in large-scale applications.

## Findings

### 1. High Sensitivity to Registration Precision
Theorem 4.1 provides a constant-factor approximation guarantee for TC, but this guarantee is conditioned on obtaining the **optimal** full-rank transport plan $P_{\sigma^*}$ in Step 1.
My audit of **Figure 10 (Page 37)** and **Table 4 (Page 33)** reveals that TC is extremely sensitive to the precision of this registration map. As the Sinkhorn regularization $\epsilon$ (which controls the "blurriness" or error in the full-rank coupling) increases from $10^{-5}$ to $10^1$, the resulting low-rank OT cost increases from **5.050 to 14.538**.

This ~3x increase in cost shows that the "constant-factor" nature of the algorithm is highly fragile and depends on a very precise (and computationally expensive) first step.

### 2. Theoretical Gap for Large-Scale Approximate Solvers
The paper evaluates TC on a large-scale dataset ($n=131,040$ mouse embryo cells). For a dataset of this size, computing an optimal full-rank plan is computationally infeasible. The authors acknowledge using **HiRef (Halmos et al., 2025b)**, a hierarchical approximate solver, for Step 1 in these cases.
However, the theoretical analysis does **not** provide a bound for the case where Step 1 is solved using an approximate or hierarchical method. Given the empirical sensitivity demonstrated in Figure 10, the provided bounds (e.g., $1+\gamma$) are likely invalid when an approximate registration map is used.

### 3. Efficiency-Accuracy Trade-off
In Table 6 (Page 34), for the largest dataset ($n=131,040$), TC achieves a low-rank OT cost of **0.389** compared to FRLC's **0.399** (a ~2.5% improvement). However, TC's runtime is **806.81s** compared to FRLC's **58.58s**.
This represents a **14x increase in runtime** for a marginal gain in cost. The paper's claim in the abstract that TC "outperforms" existing solvers is technically true for cost but misleading regarding practical utility and efficiency.

## Recommendation
The authors should:
1. Provide a theoretical sensitivity analysis that extends the approximation guarantees to $\delta$-approximate registration plans.
2. Explicitly discuss the runtime-accuracy trade-off compared to FRLC, as the current framing overstates the practical advantage of TC on large-scale datasets.
