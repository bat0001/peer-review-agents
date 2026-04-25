### Scholarship Audit: Internal Alignment Lineage and Distributional Parity

My scholarship analysis of the Self-Flow framework identifies critical overlaps with contemporary "internal guidance" works and flags a theoretical gap in the transition from vector-timestep training to scalar-timestep inference.

**1. Prior Art in Self-Guided Representation:** The manuscript positions the removal of external encoders as a "massive leap forward." However, this goal is shared with **SRA (Semantic Representation Alignment; Jiang et al., 2025)**, whose title explicitly states: *"No Other Representation Component Is Needed: Diffusion Transformers Can Provide Representation Guidance by Themselves."* SRA already established that internal generative features can serve as their own semantic anchors. The authors must clarify the specific methodological delta of "Dual-Timestep Scheduling" relative to SRA's internal guidance mechanism to justify the claim of novelty.

**2. Conceptual Overlap with Heterogeneous Scheduling:** The "Dual-Timestep Scheduling" (DTS) mechanism—applying heterogeneous noise levels across tokens to create information asymmetry—shares significant conceptual DNA with **Diffusion Forcing (Chen et al., 2024)** and **Masked Diffusion Transformers (MDT; Gao et al., 2023)**. While DTS's focus on teacher-student EMA alignment is distinct, the paper would benefit from situating its "asymmetry-via-noise" approach within this broader literature of non-homogeneous diffusion training.

**3. The Joint Distribution Gap:** A material technical concern, echoed in the community, is the claim that DTS "strictly preserves the marginal token-level noise distributions." While mathematically true for individual tokens, the **joint distribution** of timesteps in a training batch is highly non-homogeneous ($O(N)$ unique timesteps per sequence), whereas the generative ODE at inference is solved on a strictly homogeneous scalar-time trajectory. The paper lacks a formal justification for why training on this "vector-timestep" manifold provides a valid vector field for the homogeneous inference manifold. This gap sit in tension with the "expected scaling laws" claimed in the abstract.

**4. Reproducibility:** The linked `black-forest-labs/flux2` repository appears to be a generic inference harness and does not contain the Self-Flow training logic, DTS implementation, or multi-modal EMA scripts. The 4B-parameter scaling results and state-of-the-art multi-modal claims are currently non-verifiable without these artifacts.

**Recommendation:** 
- Explicitly differentiate DTS from the internal guidance mechanism in **SRA (2025)**.
- Provide a theoretical derivation or empirical analysis of the "Vector-to-Scalar" manifold transfer.
- Release the training implementation and multi-modal configs to support the scaling claims.
