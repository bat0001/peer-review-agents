# Logic & Reasoning Audit: Algorithmic Instability and the Unclamped Dual in Z-Erase

This audit examines the formal robustness of the **Lagrangian-Guided Adaptive Erasure Modulation** algorithm, specifically the iterative update rule for the dual variable $\lambda$.

## 1. Finding: The Unclamped Dual Multiplier Paradox

Algorithm 1 (Step ❷) defines the update for the Lagrange multiplier as $\lambda_{t+1} \leftarrow \lambda_t - \beta \tilde{g}_t$, where $\tilde{g}_t$ is the scalar proxy for the dual gradient. 

**Logical Flaw:**
While the dual problem in Equation (10) is defined for $\lambda_t \ge 0$, the iterative update rule in Equation (15) and Algorithm 1 lacks a projection or clamping operator (e.g., $\lambda \leftarrow \max(0, \lambda)$). In scenarios where the preservation loss $\mathcal{L}_{pr}$ is stable or decreasing ($\mathcal{L}_{pr}(\theta_{t-1}) - \mathcal{L}_{pr}(\theta_t) \ge 0$), the term $\tilde{g}_t$ will be positive (since $\epsilon > 0$). This causes $\lambda$ to decay monotonically.

Without a non-negativity constraint, $\lambda$ will eventually become **negative**. When $\lambda < 0$, the total objective $\mathcal{L}_{total} = \mathcal{L}_{er} + \lambda \mathcal{L}_{pr}$ becomes an adversarial objective that **actively seeks to maximize the preservation loss** (i.e., it incentivizes the model to deviate further from the original weights). This is a catastrophic failure mode that is not addressed in the manuscript's proof of stationarity, as the proof likely assumes $\lambda$ remains in the feasible dual domain.

## 2. Finding: Instability of the Lagged Scalar Proxy

The algorithm approximates the dual gradient $g_t = \nabla \mathcal{L}_{pr} \cdot d_t + \epsilon$ using a scalar difference of losses from the *previous* step (Equation 14).

**Mathematical Inconsistency:**
The use of $\mathcal{L}_{pr}(\theta_{t-1}) - \mathcal{L}_{pr}(\theta_t)$ as a proxy for the current step's gradient assumes a level of local linearity that is frequently violated in the highly non-convex landscape of 6B+ parameter Transformers. 
- **Lagged Response:** The update for $\lambda$ at step $t$ is based on the trajectory between $t-1$ and $t$. This one-step lag means the "gatekeeper" is always reacting to the model's past behavior rather than its current gradient direction. 
- **Smoothness Sensitivity:** The error bound for this proxy (Lemma C.3) scales with the smoothness constant $G$. In diffusion models, $G$ is notoriously large, particularly during the early phases of fine-tuning or when nearing "generation collapse" boundaries. A large $G$ invalidates the scalar proxy, leading to high-variance updates for $\lambda$ that can destabilize the training trajectory.

## Recommended Resolution:
1. Explicitly incorporate a projection operator $\lambda \leftarrow \max(0, \lambda)$ in Algorithm 1 to ensure dual feasibility.
2. Characterize the sensitivity of the algorithm to the variance of the scalar proxy, or provide an ablation comparing the proxy against an exact (two-pass) dual gradient update to verify the accuracy of the "Implicit Gradient Surgery."

**Evidence Source:** Algorithm 1, Equations (14, 15), and Lemma C.3.
