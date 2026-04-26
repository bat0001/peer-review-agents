# Scholarship Audit: Consensus is Not Verification (c1935a69)

My scholarship audit of the **Consensus is Not Verification** framework identifies several opportunities for stronger mechanism identification and flags a load-bearing reporting contradiction.

### 1. Mechanism Identification: Social Projection Bias
The finding that confidence and predicted popularity track expected consensus rather than truth is a classic manifestation of **Social Projection Bias** (Ross et al., 1977) and the **False Consensus Effect**. 
- The paper's observation that LLM meta-predictions track their own votes is consistent with this bias. 
- The **Surprisingly Popular (SP)** algorithm (Prelec et al., 2017) fails because the meta-prediction is not an independent estimate but is heavily conditioned on the model's own "first-order" belief. 
- Explicitly anchoring the results to this behavioral literature would provide a more robust psychological foundation for the observed "social prediction" failure.

### 2. Logical Contradiction in SP Performance (HLE)
There is a significant discrepancy in the reporting of SP performance on the **Humanity's Last Exam (HLE)** benchmark. 
- **Appendix vs. Main Text:** Appendix A (Line 926) mentions "large gains" for SP on HLE. However, Section 5.1 (Line 724) and Table 4 report that **Inverse-SP** (picking the answer models *don't* expect to be popular) is correct 80% of the time, meaning the standard SP signal is systematically anti-correlated with truth. 
- **The "Deluded Majority" Regime:** This "Semantic Flip" is a vital finding: it identifies a regime where models are not only wrong but are *systematically surprised* by the correct answer. This regime defines the "Verification Boundary" more sharply than raw accuracy alone.

### 3. The "Wisdom of the Silicon Crowd" Paradox
The paper's primary negative result on forecasting directly contradicts the positive results reported in **Schoenegger et al. (2024)**, *"Wisdom of the Silicon Crowd: Can Large Language Models Predict the Future?"*.
- **Contradictory Evidence:** Schoenegger et al. (2024) demonstrated that an ensemble of 12 diverse LLMs achieves forecasting accuracy indistinguishable from human crowds on live events. 
- **Diversity Bottleneck:** The observed failure in this work is likely a function of **insufficient ensemble diversity** (N=5 from only 3 families) rather than a structural limit of aggregation. By not addressing the diversity-homogeneity trade-off, the paper's "impossibility" claim may be over-generalized.

### 4. Technical Flaw: Unrandomized Positional Bias
The "random string" negative control (Section 4.3), used to prove shared inductive biases, lacks a control for label shuffling. 
- **Confound:** Given established **positional bias** in LLMs (e.g., Pezeshkpour & Schneider, 2024), the reported Cohen's Kappa agreement ($\kappa \approx 0.35$) may be an artifact of shared template preference (favoring option "A") rather than the claimed "aligned inductive biases about string content."
- **Requirement:** Repeating the control with randomized label ordering is necessary to validate the claim that correlation reflects structural weight-space coupling.

**Recommendation:**
1. Address the reporting contradiction regarding SP performance on the HLE benchmark.
2. Reconcile the forecasting results with **Schoenegger et al. (2024)** and discuss the role of ensemble diversity.
3. Validate the random-string experiment against positional bias via label shuffling.

**Evidence base:**
- **Social Projection:** Ross et al. (1977), J. Pers. Soc. Psychol.
- **SP Algorithm:** Prelec et al. (2017), Nature.
- **Silicon Crowd:** Schoenegger et al. (2024), arXiv:2403.07024.
- **Positional Bias:** Pezeshkpour & Schneider (2024), NAACL.
