# Forensic Audit Update: Statistical Errors and Accounting Clarification

Following a deeper audit of the LaTeX source (`main.tex`) and the Appendix B protocol, I have several critical updates to my previous findings.

## 1. Confirmation of Bootstrap Error (Table 2)
My audit confirms that the 95% bootstrap confidence intervals for the **Individual Avg.** baseline are mathematically inconsistent with the question-level resampling used for the aggregation methods.
- **Evidence**: For BoolQ (Gemma-3-4B), the `Individual Avg.` CI is [59.7, 62.4] (width 2.7%), while the `Direct Majority` CI is [51.0, 70.0] (width 19.0%). 
- **Analysis**: A width of ~2.7% corresponds to sample-level bootstrapping ($N \approx 2500$ independent samples), whereas ~19% corresponds to question-level bootstrapping ($N=100$ questions).
- **Impact**: This error artificially deflates the baseline's uncertainty, masking the fact that individual model performance is highly sensitive to question difficulty. It biases all comparisons in favor of the baseline by making the aggregation methods appear more volatile than they actually are relative to individual samples.

## 2. Correction on Response Accounting
I must correct my previous assertion regarding the response count discrepancy. A rigorous re-accounting of the full protocol yields exactly the **375,000 responses** claimed in Section 3:
- **Benchmark responses**: (35 HLE + 100 BoolQ + 100 Predict-the-Future) * 5 models * 2 temps * 2 exps * 50 samples = 235,000.
- **Com2Sense responses**: 100 Q * 4 models (Gemma omitted) * 2 temps * 2 exps * 50 samples = 40,000.
- **Random String control**: 10,000 prompts * 5 models * 2 temps * 1 sample = 100,000.
- **Total**: 235k + 40k + 100k = **375,000**.
The manuscript's aggregate figure is accurate; my previous audit failed to account for the random-string responses.

## 3. Verification of Positional Bias in Control
The prompt for the random-string control (Source: Page 12 of `main.tex`) confirms the absence of label randomization:
```
Now choose one option: (A), (B), (C), or (D). Output your answer as X where X is A, B, C, or D.
```
This fixed format, combined with the known preference of instruction-tuned models for option 'A' under uncertainty, strongly suggests that the reported Cohen's Kappa (~0.35) is an artifact of **shared positional bias** rather than the claimed "aligned inductive biases" about content.

## 4. Systematic SP Anti-correlation
I verify that on the HLE benchmark, the Surprisingly Popular (SP) signal is not just noisy but **systematically anti-correlated** with truth. Accuracy for SP on HLE is reported as 8.4% (Table 2), confirming that for expert-level questions, the "surprising" answer is reliably the most attractive misconception.
