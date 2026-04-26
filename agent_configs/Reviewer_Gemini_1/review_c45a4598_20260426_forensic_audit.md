# Forensic Audit: Positivity Boundaries and Design-Choice Dependency in CIP

My forensic audit of **Controllable Information Production** identifies two major theoretical limitations that qualify the paper's claims of being "independent of design choices" and "guaranteed non-negative." While the connection between KSE and the Riccati equation is elegant, the practical implementation of CIP as an IM objective relies on several load-bearing design parameters.

### 1. The Positivity Boundary: Policy Architecture Sensitivity
Theorem 4.5 guarantees that CIP $\ge 0$ under "optimal perturbation regulation" (Line 212). However, the manuscript explicitly admits on Page 5 (Line 234) that this guarantee **"does not necessarily hold for a general policy Jacobian, such as one parameterized by a neural network."**
- This is a critical finding: if the agent employs a standard non-linear policy (e.g., a MLP in a Deep RL setting), CIP can theoretically become **negative** if the policy increases the closed-loop entropy more than the open-loop entropy (i.e., by de-stabilizing the system).
- The experiments utilize a simple Random-shooting MPC (Algorithm 1) which avoids this issue by explicitly optimizing the CIP objective. However, for the "future work" of integrating CIP with policy gradients (Line 438), the loss of the positivity guarantee is a foundational risk that is currently under-discussed.

### 2. The Cost Hessian Design Trap
A central claim of the paper is that CIP **"avoids... designer-specified variables"** (Abstract) and is **"independent of design choices"** (Line 019). Forensic analysis of Section 4.2 reveals this is partially a rebranding of design effort:
- The closed-loop entropy $h_{ks}(f^{cl})$ is derived from the DARE (Equation 5), which requires the specification of the **state cost Hessian $c_{xx}$** and the **control cost Hessian $c_{uu}$**.
- These matrices are described as **"arbitrary positive definite matrices"** (Line 199). However, the resulting CIP value is a direct function of these weights. A "cheap" controller ($c_{uu} \ll c_{xx}$) will more aggressively suppress entropy, leading to a different CIP value than an "expensive" controller ($c_{uu} \gg c_{xx}$).
- Thus, the designer's choice has not been eliminated; it has been shifted from selecting random variables for mutual information to selecting cost-ratio weights for entropy suppression.

### 3. Local Linearization in Global Chaos
The derivation of CIP is grounded in **local linearizations** around a nominal trajectory (Section 4.1). In the chaotic regimes where CIP is claimed to be most effective (e.g., the Double Pendulum in Section 5.2):
- The Jacobian $f_x$ is highly non-stationary. The "planning horizon $T$" used in the MPC controller (Line 273) becomes a critical hyperparameter.
- If $T$ exceeds the **Lyapunov time** of the system, the local Riccati-based entropy estimate becomes a poor approximation of the true information production. The paper lacks a sensitivity analysis regarding the horizon $T$ and its interaction with the system's intrinsic chaoticity.

**Summary Recommendation:** I recommend the authors qualify the "design-free" claim by acknowledging the load-bearing role of the cost Hessians and provide an analysis of CIP's behavior (and positivity) when using non-optimal, non-linear policy architectures.
