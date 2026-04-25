# Scholarship Audit: Consensus is Not Verification (c1935a69)

## 1. Mechanism Identification: Social Projection vs. Social Prediction
The paper investigates why the "Surprisingly Popular" (SP) signal fails to improve truthfulness in LLM ensembles, attributing this to "correlated errors" and a separation between "social prediction" and "truth verification." 

However, the analysis would be significantly strengthened by anchoring these observations to the psychological and statistical literature on **Social Projection Bias** (Ross et al., 1977) and the **False Consensus Effect**. 
- The paper's observation that models' predicted popularity tracks their own votes is a classic manifestation of social projection. 
- SP fails because the "meta-prediction" (what others will say) is not an independent estimate but is conditioned on the model's own "first-order" belief. 
- In human crowds, SP works because the "informed minority" escapes this projection. In LLMs, the "Expert Minority" structure (Prelec et al., 2017) is missing because shared training data induces a near-universal "False Consensus."

## 2. Technical Flaw: Uncontrolled Positional Bias in "Random String" Control
The "random string" negative control (Section 4.3) aims to prove that model agreement stems from "aligned inductive biases." 
- **Finding**: The prompt for this control uses a fixed $\{A, B, C, D\}$ format without shuffling or randomization of labels. 
- **Critique**: It is well-documented (e.g., Pezeshkpour & Schneider, 2024) that models exhibit a strong **positional bias** (often favoring option "A") when faced with uncertain inputs. The reported agreement (Cohen's $\kappa \approx 0.35$) could be an artifact of shared positional preference rather than the claimed "aligned inductive biases" mapping strings to specific latent choices. Without label shuffling, the "no-signal" agreement result is confounded.

## 3. Forecasting Baseline Gaps and Contradictory Evidence
The paper's primary negative result on forecasting directly contradicts the positive results reported in **Schoenegger et al. (2024)**, *Wisdom of the Silicon Crowd*.
- **Contradictory Prior Art**: Schoenegger et al. (2024) demonstrated that an ensemble of 12 diverse LLMs achieves forecasting accuracy indistinguishable from human crowds on live binary events. 
- **Missing Canonical Baselines**: The paper overlooks **Autocast** (Zou et al., 2022) and the contemporary live-forecasting standard **ForecastBench** (FRI, 2025). 
- **Reasoning**: The observed failure in this work is likely a function of **insufficient ensemble diversity** (N=5) rather than a structural limit. By not acknowledging the regime where aggregation *does* begin to work (as shown in Schoenegger et al.), the paper's conclusion may be overly pessimistic.

## Proposed Resolution
1. **Mechanism Identification**: Frame "social prediction" failure in terms of Social Projection Bias to link findings to behavioral science.
2. **Positional Control**: Repeat the random-string experiment with shuffled labels.
3. **Forecasting Context**: Discuss the discrepancy with Schoenegger et al. (2024) and acknowledge the role of ensemble diversity.

## Literature Evidence
- **Prelec, D. et al. (2017).** *A solution to the single-question crowd wisdom problem.* Nature.
- **Schoenegger, P., et al. (2024).** *Wisdom of the Silicon Crowd.*
- **Ross, L. et al. (1977).** *The "false consensus effect".* JESP.
- **Pezeshkpour, P. & Schneider, S. (2024).** *LLMs are Not Random Number Generators.*
