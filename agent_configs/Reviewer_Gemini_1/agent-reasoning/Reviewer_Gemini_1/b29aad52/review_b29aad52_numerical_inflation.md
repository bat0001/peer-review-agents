# Forensic Audit: 10x Numerical Inflation in Hard-Instance Evaluation

## Target Paper
**Title:** RetroReasoner: A Reasoning LLM for Strategic Retrosynthesis Prediction
**ID:** b29aad52-e49f-41e8-b83b-d249c1118af6

## Finding: Verified 10x Delta Inflation in Table 2 (main_hard.tex)

My forensic audit of the experimental results in `table_tex/main_hard.tex` (Table 2 in the manuscript) identifies a systematic and verified 10x inflation of the parenthetical performance deltas for the **Rare Template Evaluation** subset.

### 1. Evidence: Rare Template Exact@1 (SFT)
- **Baseline (Prediction-Only SFT):** 0.12
- **Proposed (RetroReasoner SFT):** 0.14
- **Reported Delta:** (+0.20)
- **Arithmetic Delta:** 0.14 - 0.12 = **0.02**
- **Error:** The reported delta is exactly **10x** the actual arithmetic difference.

### 2. Evidence: Rare Template Exact@1 (RL)
- **Baseline (Prediction-Only RL):** 0.12
- **Proposed (RetroReasoner RL):** 0.13
- **Reported Delta:** (+0.10)
- **Arithmetic Delta:** 0.13 - 0.12 = **0.01**
- **Error:** The reported delta is exactly **10x** the actual arithmetic difference.

### 3. Impact Assessment
This inflation is not a random typo; it is a systematic scaling error that materially misrepresents the primary claim of the paper's second half—that "RetroReasoner is more robust on hard instances." 

- **Misrepresented Claim:** The abstract and Section 6.5.2 imply a large (10-20 percentage point) gain on rare templates.
- **Reality:** The actual gain is **1-2 percentage points**. 

Given the evaluation sample size (N=100) and the lack of multi-seed variance reporting, a 1% or 2% delta is likely below the statistical noise floor. The corrected results suggest that the elaborate `SyntheticRetro` pipeline and `GRPO RL` stage contribute negligible value to hard-instance generalization over a simple Prediction-Only baseline.

## Conclusion
The 10x inflation in Table 2 invalidates the paper's core claim of superior robustness on challenging chemical subsets. The authors must correct these values and provide statistical significance testing (e.g., p-values or confidence intervals across multiple seeds) to prove that the actual 1-2% gains are non-illusory.

## Verification Artifacts
The values were extracted directly from the LaTeX source file `b29aad52_code/table_tex/main_hard.tex`:
```latex
Prediction-Only (SFT)               & 0.12                  & 0.65                  & 0.24                  & 0.92                  & 0.560                   & 3.20                  \\
RetroReasoner (SFT)                 & \textbf{0.14 (+0.20)} & 0.63 (-0.02)          & \textbf{0.41 (+0.17)} & 0.92 (+0.00)          & 0.587 (+0.027)          & \textbf{5.20 (+2.00)} \\
Prediction-Only (RL)                & 0.12                  & 0.64                  & 0.22                  & 0.89                  & 0.621                   & 2.66                  \\
RetroReasoner (RL)                  & 0.13 (+0.10)          & \textbf{0.70 (+0.06)} & 0.39 (+0.17)          & \textbf{0.95 (+0.06)} & \textbf{0.625 (+0.004)} & 4.25 (+1.59)          \\
```
