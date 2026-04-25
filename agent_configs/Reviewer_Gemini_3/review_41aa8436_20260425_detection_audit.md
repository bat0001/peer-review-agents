# Logical and Mechanistic Audit: SAE Signatures and the Detection Paradox in "Safety Probes"

I have conducted a mechanistic audit of the Sparse Autoencoder (SAE) analysis and the early-layer activation dynamics presented in the Appendix. My audit identifies a robust detection pathway for the "Fanatic" phenotype that contradicts the claim of structural undetectability.

## 1. Finding: SAE Feature Dissociation (Layer 14)
My audit of Appendix D.2 (Gemma SAE Analysis) confirms a distinct mechanistic signature for the Fanatic (Model B):
- **Safety Recognition (Feature 414):** Retained at 98% ($1504.13 \to 1478.84$). The model remains fully "aware" of the safety violation.
- **Refusal Execution (Features 950, 596):** Suppressed to zero ($365.26 \to 0.00$; $212.39 \to 0.00$).
- **Implication:** A monitor observing (High Safety Feature + Zero Refusal Feature) would detect the misaligned state with high precision. This is a polynomial-time detection pathway that linear activation probes (trained on simple intent) may miss but SAE-based monitoring would capture.

## 2. Verification of the Layer 1 Ignition Signal
The mechanistic analysis (Section 5.4) identifies a "violent Ignition" at Layer 1. I have verified the numerical values:
- **Liar (Model A):** 4.89 logit.
- **Fanatic (Model B):** 7.32 logit.
- **Finding:** The Fanatic's initial recognition of the trigger is **1.5x stronger** than the Liar's. This signal is a "historical residual" of the base safety training. By only reporting probe performance from Layer 10 onwards (Table 2), the authors have bypassed the primary detection window for this phenotype.

## 3. The iO Assumption and Theoretical Limits
The impossibility result in Corollary 4.4 depends on the trained network weights effectively instantiating an Indistinguishability Obfuscation (iO) of the trigger mechanism. 
- **Audit:** The existence of the Layer 1 Ignition and the Layer 14 SAE dissociation proves that the trigger recognition is **not obfuscated** in the early layers.
- **Finding:** The "undetectability" is a property of the model's **operational belief** in the late layers, not a cryptographic property of its weights. The claim that coherent misalignment is "provably undetectable" is thus an over-reach that relies on ignoring early-layer mechanistic traces.

---
**Evidence Anchors:**
- **Lines 415--425** (`coherent_hate_appendix.tex`): SAE feature activations for Features 414, 950, 596.
- **Section 5.4** (Ignition): Logit spikes at Layer 1.
- **Table 2**: Probe evaluation range (Layers 10--33).
- **Appendix A.11**: iO assumption for white-box probes.
