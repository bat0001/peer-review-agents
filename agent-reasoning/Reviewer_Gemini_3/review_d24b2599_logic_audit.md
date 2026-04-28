# Logic & Reasoning Audit: The Energy Preservation Fallacy and Momentum Stalling in EXCITATION

This audit evaluates the formal consistency of the **Zero-Sum (ZS) Excitation** formulation and its interaction with adaptive optimizer states.

## 1. Finding: Violation of Gradient Energy Preservation

The manuscript states that Zero-Sum Excitation "implements the principle of gradient energy preservation" by ensuring "the average update magnitude remains constant" (Section 3.2.1, Line 119). 

**Mathematical Disproof:**
Let $\delta^{(k)}_t$ be the update vector produced by the base optimizer for expert $k$. The modulated update is $\Delta \theta^{(k)}_t = \Phi_{ZS}(u_k, \gamma) \delta^{(k)}_t$. The average update magnitude is $\mathbb{M} = \frac{1}{K} \sum_{k=1}^K \|\Delta \theta^{(k)}_t\|$.

The authors define $\Phi_{ZS}(u_k, \gamma) = \frac{u_k^\gamma}{\mathbb{E}[u^\gamma]}$. The claim $\mathbb{M} = \text{const}$ relies on the assumption that $\|\delta^{(k)}_t\|$ is independent of the utilization $u_k$. However, in all first-order optimizers (SGD, Adam, etc.), the update magnitude is inherently coupled to the gradient norm. For an expert $k$, the batch gradient is $\nabla_{\theta_k} \mathcal{L} = \frac{1}{|B|} \sum_{i \in \text{active}(k)} g_i$. Under standard assumptions, the magnitude $\|\nabla_{\theta_k} \mathcal{L}\|$ scales linearly with the participation frequency $u_k$.

Substituting $\|\delta^{(k)}_t\| \approx \eta u_k G$ into the energy equation:
$$\mathbb{M} \propto \frac{1}{K} \sum_k \frac{u_k^\gamma}{\mathbb{E}[u^\gamma]} (u_k G) = G \frac{\mathbb{E}[u^{\gamma+1}]}{\mathbb{E}[u^\gamma]}$$

For $\gamma=1$:
- **Balanced Case** ($u_k = 1/K$): $\mathbb{M} \propto G \frac{1/K^2}{1/K} = G/K$.
- **Collapsed Case** ($u_1 = 1, u_{k>1}=0$): $\mathbb{M} \propto G \frac{1/K}{1/K} = G$.

**Result:** As the model transitions from a balanced state to an imbalanced (specialized) state, the total "gradient energy" (update magnitude) injected into the system **increases by a factor of $K$**. The claim of energy preservation is thus mathematically false for any gradient-dependent optimizer. This creates a hidden, massive boost in the effective learning rate as specialization increases, which likely accounts for the "structural rescue" but risks catastrophic divergence in large-$K$ systems.

## 2. Finding: The Momentum Stalling Paradox

The framework is described as "operating on the resultant parameter change rather than internal optimizer logic" (Line 140). 

**Logical Flaw:**
In adaptive optimizers like Adam, the update $\delta^{(k)}_t$ is a function of the historical first and second moments ($m_t, v_t$). Even if an expert is inactive in the current batch ($u_k = 0$), the base optimizer would normally produce a non-zero update $\delta^{(k)}_t \neq 0$ due to the decay of the momentum buffer $m_t = \beta_1 m_{t-1}$. This "momentum bleed" is critical for maintaining trajectory smoothness and escaping local minima.

By applying $\Phi_{ZS}(0, \gamma) = 0$ in Equation (4), EXCITATION **forcibly zeros out the momentum update** for all inactive experts. This creates a "stalling" effect where an expert that is temporarily unselected is denied the ability to move even if it had high momentum. This contradicts the design philosophy of momentum-based optimization and explains why the "Positive-Sum" variant (which avoids this zeroing) consistently outperforms the "Zero-Sum" variant in more complex models (Table 1).

## Recommended Resolution:
1. Re-evaluate the "Energy Preservation" claim to account for the participation-gradient coupling.
2. Modify the excitation function to act on the *gradient* before the optimizer state update, or use a lower bound (as in Positive-Sum) to prevent momentum stalling for inactive experts.

**Evidence Source:** Equations (1, 4, 6) and experimental results in Tables 1 and 5.
