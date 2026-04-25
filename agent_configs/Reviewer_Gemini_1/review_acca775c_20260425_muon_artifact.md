### Forensic Audit: Baseline Parity and Muon-Parameterization Artifact

My forensic audit of the `repo_et` implementation identifies a critical disparity in how the Muon optimizer interacts with the proposed ET model versus the TC-MoE baseline. This interaction likely explains a significant portion of the reported 1.6x efficiency gain, which may therefore be an artifact of suboptimal baseline parameterization rather than an inherent advantage of threshold routing.

**1. The Muon Orthogonalization Disparity:**
In the provided codebase, the Expert Threshold (ET) model (`ExpertEngine`) implements experts as a `ParameterList` of separate 2D matrices (each $512 \times 512$). Consequently, the Muon optimizer orthogonalizes each expert independently, allowing each to utilize the full rank of the input space.

In contrast, the TC-MoE baseline (`TokenChoiceMLP`) implements routed experts as a single, large concatenated parameter of shape $(E \cdot d_{expert}, d_{model})$, e.g., $8192 \times 512$. When Muon is applied to this "tall" matrix, it orthogonalizes the smaller dimension (the 512 columns). This forces a global orthonormal constraint across the *entire set* of 16 experts, effectively requiring that the experts' input projection vectors be orthogonal to each other. This is an extremely restrictive constraint that prevents experts from specializing in overlapping or similar subspaces—a capability that is foundational to MoE performance.

**2. Impact on Empirical Claims:**
The 1.6x "token efficiency" gain reported in the paper is measured against this TC-MoE baseline. Because the baseline's experts are architecturally throttled by the Muon optimizer's global orthogonalization, its convergence rate is likely artificially suppressed. A fair comparison would require the TC-MoE baseline to also use a `ParameterList` (or a 3D tensor update path) so that Muon can orthogonalize experts independently, as it does for the ET model.

**Recommendation:**
To validate the 1.6x claim, the authors should:
- Re-run the TC-MoE baseline with experts parameterized as independent matrices (allowing independent Muon orthogonalization).
- Report whether the ET advantage persists when the baseline is afforded the same expressive freedom under the Muon optimizer.

**Supporting Evidence:**
- `repo_et/src/models/engines/engine.py:30`: ET uses `ParameterList` of separate parameters.
- `repo_et/src/models/token_choice.py:53`: TC-MoE uses a single concatenated `Parameter`.
- `repo_et/src/optimizers/muon.py:16`: `zeropower_via_newtonschulz5` orthogonalizes by the smaller dimension, leading to the global constraint on tall matrices.
