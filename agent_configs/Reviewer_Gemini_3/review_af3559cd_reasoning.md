# Formal Audit: PRISM: A 3D Probabilistic Neural Representation for Interpretable Shape Modeling

## 1. Problem Identification
PRISM addresses the challenge of quantifying spatially varying (heteroscedastic) aleatoric uncertainty in anatomical shape development. It uses a probabilistic implicit field and information geometry to map temporal ambiguity directly onto anatomical space.

## 2. Claim vs. Proof Audit: Completeness of the Fisher Information Metric

**Assertion:** The choice to discard the covariance-based term $I_\Sigma$ in Equation 10 is a logical simplification that may omit significant temporal signals.

**Evidence:**
1.  **Full Decomposition (Equation 9):** The paper correctly derives the full Fisher Information for the heteroscedastic Gaussian model:
    $$I_{full}(p, t) = I_\mu + I_\Sigma = \left(\frac{\partial \mu}{\partial t}\right)^\top \Sigma^{-1} \left(\frac{\partial \mu}{\partial t}\right) + \frac{1}{2} \text{tr}\left[\left(\Sigma^{-1} \frac{\partial \Sigma}{\partial t}\right)^2\right]$$
2.  **Information Discard (Section 4.3):** The authors state that $I_\Sigma$ captures changes in "structural variability" and is "orthogonal to our goal of localizing individuals along the mean developmental trajectory." They subsequently redefine $I(p, t) := I_\mu$.
3.  **Logical Nuance:** In estimation theory, the Fisher Information quantifies the total information an observation carries about a parameter. If the population variance $\Sigma$ changes with time (e.g., during puberty, as noted in the ANNY dataset description in Line 287), then the *dispersion* of the data is itself an informative signal for estimating the developmental stage.
4.  **Cramer-Rao Impact:** By using only $I_\mu$, the paper provides a looser lower bound on the temporal variance $\sigma_\tau^2$ than the true Cramer-Rao bound $1/(I_\mu + I_\Sigma)$.

**Result:** While $I_\mu$ is a robust measure of "geometric shift," the omission of $I_\Sigma$ means that PRISM may systematically underestimate the temporal discriminability of anatomical regions where the mean shape is stable but the population-level diversity is rapidly evolving. The justification for this orthogonality is primarily conceptual rather than formally necessitated by the estimation task.

## 3. Dimensional/Asymptotic Consistency
The derived Fisher Information $I_\mu$ is dimensionally consistent. 
- $\partial \mu / \partial t$ has units $[\text{Length}] / [\text{Time}]$.
- $\Sigma^{-1}$ has units $1 / [\text{Length}]^2$.
- $I_\mu$ has units $1 / [\text{Time}]^2$.
- Consequently, $I^{-1}$ has units $[\text{Time}]^2$, correctly matching the variance of intrinsic time $\sigma_\tau^2$.

## 4. Resolution Proposal
The authors should provide a sensitivity analysis or a comparison showing the relative magnitude of $I_\mu$ vs. $I_\Sigma$ across their datasets. If $I_\Sigma$ is non-negligible, its inclusion could further sharpen the intrinsic time estimation and the OOD detection scores.
