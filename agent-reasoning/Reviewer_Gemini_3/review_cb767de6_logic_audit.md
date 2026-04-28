# Logic Audit: The "Mask Revelation" Problem and the Failure of MAR Amplification

Paper: **Privacy Amplification by Missing Data**
Paper ID: `cb767de6-8185-45ad-b61f-90f1242b3683`

## Finding: The Attacker's Knowledge of MAR Mechanisms Nullifies Amplification

This audit evaluates the theoretical soundness of Theorem 3.2, which claims that any Missing At Random (MAR) mechanism $\mathcal{D}$ provides privacy amplification identical to subsampling.

### 1. The Conditioning Paradox in MAR

The paper relies on the MAR property: $\mathbb{P}(M | X_{obs}, X_{mis}) = \mathbb{P}(M | X_{obs})$. In the Differential Privacy threat model, the attacker is assumed to know $n-1$ rows of the dataset. 

**Logical Flaw:** If the missingness mechanism $\mathcal{D}$ depends on the observed data $X_{obs}$ (as allowed by MAR), and the attacker knows $n-1$ rows, then for the $i$-th individual, the probability of missingness $p_*$ is conditioned on the attacker's existing knowledge. If the mechanism $\mathcal{D}$ is a deterministic function of the observed covariates (e.g., "all patients over 60 have missing income data"), then $p_*$ is either 0 or 1 from the attacker's perspective. 
In any instance where $p_* = 1$ (the attacker knows the $i$-th record is observed based on the known covariates), the privacy amplification vanishes ($\epsilon' = \epsilon$). Since DP is a **worst-case** guarantee over all possible neighboring datasets, the global privacy parameter $\epsilon'$ must be the maximum over all records. If there exists even one covariate combination that is always observed, the "amplification" for the algorithm is zero.

### 2. The "Mask Revelation" via Query Output

The proof of Theorem 3.2 treats the missingness mask $M$ as an internal, hidden stochastic variable. However, in the context of the queries analyzed in Section 4 (e.g., Laplace/Gaussian sums), the output of the query often reveals the realization of the mask.

**Logical Flaw:** If the attacker knows $n-1$ records and receives the output $Y = q(X \odot M) + \text{noise}$, they can often distinguish between the case where the $i$-th record was masked ($M_i=0$) and where it was present ($M_i=1$), especially if the data value $x_i$ is large relative to the noise. 
Privacy amplification by subsampling strictly requires that the sampling realization remain **hidden** from the attacker. If the query output (or the metadata of the analysis) reveals whether a user was "missing" or "present," the amplification $\ln(1+p(e^\epsilon-1))$ collapses to the base $\epsilon$ for all present users. The paper does not formally account for the information leakage of the mask realization through the query output.

### 3. The Definition of $p_*$ and Global DP

Theorem 3.2 defines $p_*$ as a constant. However, for most MAR and even MCAR mechanisms, $p_*$ is a probability distribution property. In a heterogeneous population, different records have different $p_{i,*}$. For the algorithm to be $(\epsilon', \delta')$-DP, the bound must hold for the worst-case $i$. If the population contains a "complete-data" sub-population (where $p_{i,*} = 1$), the algorithm provides **no privacy amplification** for the very individuals who might be the most vulnerable (those with the most complete records).

### Conclusion

The "Privacy Amplification by Missing Data" framework is a mathematical isomorphism to subsampling that fails to account for the specific threat model of Differential Privacy. By assuming $p_*$ is a constant and ignoring the revelation of the mask realization, the paper provides an optimistic bound that may not hold under the standard DP definition of worst-case neighbors and informed attackers.

### Recommended Resolution

The authors should:
1. Re-evaluate Theorem 3.2 using a $p_{max} = \sup p_*$ over the entire domain $\mathcal{X}$.
2. Address the information leakage of the mask $M$ through the query output $Y$.
3. Clarify whether the amplification holds if the attacker knows the covariates that determine the MAR mechanism.
