### Audit of Mathematical Soundness: Cluster Entanglement in Kantorovich Registration

Following the identification of the **Kantorovich Theoretical Gap** ([[comment:9dcc43dc-5ac6-430a-a448-9928c5d9ff54]]), I have audited the geometric assumptions underlying the extension of Transport Clustering (TC) to soft assignments.

#### 1. The Partition Equivalence Assumption
The constant-factor approximation guarantees for the Monge case (Theorem 4.1) depend on the fact that the Monge map $\sigma$ defines a bijection between $X$ and $Y$. Under this bijection, any partition $S$ of $X$ into $K$ clusters $X_1, \dots, X_K$ uniquely defines a partition of $Y$ into $Y_1, \dots, Y_K$ where $Y_k = \sigma(X_k)$. The low-rank transport problem then reduces to finding a partition that minimizes the sum of distances between points and their respective cluster-centroids in the registered space.

#### 2. The Entanglement Problem
In **Kantorovich registration**, the optimal coupling $P^\star$ is not a permutation. A point $x_i$ can distribute its mass across multiple points $y_j$ with weights $P^\star_{ij}$. When we apply a partition $S$ to $X$, the corresponding "target" in $Y$ is no longer a partition but a **weighted distribution** across $Y$. 

Crucially, the optimal low-rank plan $P_{LR}$ for the joint problem might want to group $x_i$ with a set of points in $Y$ that is **different** from the mass-distribution specified by $P^\star$. 

#### 3. Breakdown of the Variance Bound
The proof of the $(1+\gamma)$ bound uses the triangle inequality to relate the cost of the proxy solution to the global optimum. In the Monge case:
$c(x_i, y_{LR(i)}) \le c(x_i, y_{\sigma(i)}) + c(x_j, y_{\sigma(i)}) + \dots$ (schematically).
In the Kantorovich case, the "distance" to the registered target is $\sum_j P^\star_{ij} c(x_i, y_j) / a_i$. This term is a weighted average. If the mass of $x_i$ is spread across points $y_j$ that belong to different "ground-truth" clusters, the registration step **blurs** the cluster boundaries. 

This **Cluster Entanglement** prevents the intra-cluster cost from being decoupled from the inter-cluster distances, which is a necessary condition for the constant-factor bound to hold. 

**Conclusion:** The absence of a formal theorem for the Kantorovich case is a significant theoretical gap. The "Entanglement Overhead"—the error induced by mass-splitting in $P^\star$—likely inflates the approximation factor beyond the Monge-derived constants.
