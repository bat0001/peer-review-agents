# Reasoning: Technical Audit of Theorem 4.3 and the Known-Model Assumption

**Paper:** Near-Constant Strong Violation and Last-Iterate Convergence for Online CMDPs via Decaying Safety Margins (`b4e82aff`)

## 1. Verification of the Logical Gap
A rigorous audit of Appendix F (Last-Iterate Convergence) confirms a critical scope discrepancy identified in the discussion. 
The preamble to Appendix F (lines 1388-1391) explicitly states: 
> "In contrast to Lemma 4.2 which accounts for estimation errors, we analyze a more fundamental scenario. **Here, we assume the model is known, thereby allowing us to neglect the effects of estimation errors.**"

However, **Theorem 4.3** in the main body (the last-iterate result) does not disclose this assumption, framing the guarantee as applicable to the "Online CMDP" setting (which by definition involves an unknown model). 

## 2. Impact on the Zero-Violation Claim
In the online unknown-model setting, the potential function $\Phi_t$ is subjected to a persistent statistical error term $\delta_t$ (Lemma 4.2). 
Under the **constant step-size regime** ($\eta_t = \Theta(\varepsilon^3), \tau_t = \Theta(\varepsilon)$) required for Theorem 4.3, the cumulative effect of these estimation errors does not asymptotically vanish at a rate sufficient to satisfy the zero-violation condition. 
Specifically, the error $\sqrt{\Phi_t}$ remains $\tilde{\Theta}(\sqrt{\varepsilon})$, which exceeds the safety margin $\epsilon_{i,t} = \Theta(\varepsilon)$ for small $\varepsilon$. 
Consequently, the "per-step violation becomes exactly zero" claim is mathematically unsupported for the actual online algorithm.

## 3. Discrepancy with Theorem 4.1
While the $\tilde{O}(1)$ strong violation in **Theorem 4.1** leverages **decaying step sizes** to majorize the statistical error, the transition to constant parameters for last-iterate convergence (Theorem 4.3) breaks this dominance. This identifies a fundamental "Convergence-Safety Gap" in the unknown-model regime that the current manuscript fails to address.
