# Reasoning and Evidence for Logic & Reasoning Audit of MetaOthello

## Finding: Context-Dependent Routing and the Distinction between Policy and World-Model Selection

Following a logical audit of the results presented in Sections 5.5 (Diverging games) and 5.6 (Out-of-distribution world modeling), I have identified a significant mechanistic distinction in how the Transformer handles game-identity arbitration depending on the "distance" between the generative processes.

### 1. The Variable Depth of the "Routing Layer"
The manuscript identifies **Layer 5** as the pivotal "routing layer" for the **Classic-NoMidFlip** pair (Line 383, Figure 5c). However, for the **Classic-DelFlank** pair—where the games diverge much earlier and more drastically—the causal peak for steering shifts significantly forward to **Layers 2 and 3** (Line 402, Figure 6a). 

**Evidence:**
- **Figure 5(c):** Steering at Layer 5 for NoMidFlip maximizes the shift in model output ($\Delta \alpha$), while steering at early layers (1-4) has little effect.
- **Figure 6(a):** Steering at Layer 5 for DelFlank has "essentially no effect" ($\Delta \alpha \approx 0$), while steering at Layers 2-3 achieves a normalized $\Delta \alpha \approx 0.75$.

This suggests that the "arbitration layer" is not a fixed architectural property of the 8-layer Transformer, but is dynamically determined by the timescale and magnitude of divergence in the data-generating processes.

### 2. Policy Routing vs. World-Model Selection
A more profound distinction exists in the *downstream impact* of these interventions. In the highly similar NoMidFlip case, steering at the routing layer (L5) changes the model's output but **fails to correct the internal board representation** in subsequent layers. In the dissimilar DelFlank case, early-layer steering (L2-3) **causally improves the downstream board representation** (Line 411, Figure 6b).

**Derivation of the "Routing Paradox":**
- **For NoMidFlip (Line 379):** "this intervention [at Layer 5] is only associated with a negligible change in the fidelity of the downstream NoMidFlip board state representations."
- **For DelFlank (Line 415):** "This causal effect on downstream representations distinguishes DelFlank from NoMidFlip, where Layer 5 steering changed model outputs but did not improve board probe accuracy at later layers."

**Logical Conclusion:**
For similar tasks (NoMidFlip), the model performs **Late-Stage Policy Routing**: it shares a common world model and simply overrides the output head based on a game-identity signal. For dissimilar tasks (DelFlank), the model performs **Early-Stage World-Model Selection**: the game-identity signal at Layers 2-3 actually "switches" the representational track, repairing the internal state for the chosen world.

This identified bifurcation in "routing modes" is a high-signal finding that explains why linear steering is effective for some multi-task conflicts but not others.

### 3. Dimensional Consistency of the Alpha Score
I have verified the dimensional and theoretical consistency of the performance metric $\alpha$ defined in Equation 7:
$$\alpha(\theta | s) = 1 - \frac{D_{KL}(P_{GT} \parallel Q_\theta)}{D_{KL}(P_{GT} \parallel U)}$$
The normalization correctly accounts for varying entropy across move sequences. Under a random guessing model ($Q_\theta = U$), $\alpha=0$; under a perfect model ($Q_\theta = P_{GT}$), $\alpha=1$. This metric provides a sound basis for comparing performance across games with vastly different branching factors (e.g., DelFlank vs. NoMidFlip).
