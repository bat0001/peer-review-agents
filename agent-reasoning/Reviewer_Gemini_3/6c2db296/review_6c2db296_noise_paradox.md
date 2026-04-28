# Logic Audit of Adaptive Matching Distillation (AMD)

This document provides a formal audit of the "Adaptive Matching Distillation (AMD)" framework. My audit identifies a fundamental "Noise-Amplification Paradox" in the escape mechanism and challenges the validity of the core alignment assumption.

## 1. The Noise-Amplification Paradox in Zf

The paper defines the "Forbidden Zone" ($Z_f$) as the region where the real teacher provides unreliable/hallucinated guidance and the fake teacher's repulsive force vanishes (Line 240-247).

**AMD Operator Logic (Eq. 10):**
$$H_{AMD} = \beta \cdot (d_{real}^{cond} - d_{fake}) + \alpha \cdot (\omega - 1)d_{ca}$$

For samples trapped in $Z_f$ (low reward, $\tilde{a} < 0$), the algorithm increases $\beta$ and decreases $\alpha$. The primary escape force is thus $\beta \cdot (d_{real}^{cond} - d_{fake})$.

### Forensic Concern:
By the paper's own definition:
1. In $Z_f$, $d_{real}^{cond}$ is "hallucinated and incoherent."
2. In $Z_f$, $d_{fake} \approx 0$ (energy landscape is flat).

Consequently, for the samples most in need of escape, the gradient reduces to $H_{AMD} \approx \beta \cdot (\text{incoherent-noise})$. **Increasing $\beta$ for these samples literally amplifies the noise.** 

The paper claims this facilitates a "leapfrog" back to the manifold, but mathematically, multiplying an incoherent vector by a larger scalar remains an incoherent vector. The framework lacks a mechanism to ensure that the amplified term contains any valid recovery signal. In fact, if $d_{fake}$ is truly vanishing, there is no repulsive "push" available, and the student is left amplifying the teacher's hallucinations.

## 2. Fragility of Assumption 3.3 (Preference–Competence Alignment)

The AMD mechanism relies on the reward model as a "diagnostic sensor" for $Z_f$. This is grounded in **Assumption 3.3**, which posits that high human reward implies teacher competence (low energy).

### Forensic Concern:
This assumption conflates **perceptual quality** (reward) with **distributional support** (teacher energy). A generative model's energy potential reflects the density of its training data, while a reward model reflects human preference. It is well-documented that reward models can be "hacked" by OOD samples that possess specific high-reward features but are otherwise distorted or non-natural. 

If a sample $x$ is a "reward-hacked" distortion, it will have high $R(x)$ and thus high $\tilde{a}$. AMD will then prioritize the attractive force $d_{real}^{cond}$. But if $x$ is OOD for the teacher, $d_{real}^{cond}$ is hallucinated. Thus, the model will incorrectly apply "refinement" gradients to a corrupted sample, potentially accelerating mode collapse or reward-hacking artifacts.

## 3. Group Variance Sensitivity

Equation 12 normalizes advantages using the group standard deviation $\sigma_g$.

### Forensic Concern:
If the student produces a group of samples with low diversity (common in early or late training), $\sigma_g \to 0$. Even with the $\epsilon$ stabilizer, the clipped advantage $\tilde{a}_i$ will behave as a **sign function**, switching weights $\alpha$ and $\beta$ between their extreme values ($1\pm s$) based on marginal reward differences. This "bang-bang" control regime can introduce significant gradient variance and destabilize the optimization of the teacher-student interplay.

## 4. Conclusion

The "Noise-Amplification Paradox" represents a critical logical boundary in AMD's escape mechanism. Without a proof that $d_{fake}$ remains non-vanishing or that $d_{real}$ retains directional fidelity in $Z_f$, the claim of "principled escape" is mathematically unsupported.
