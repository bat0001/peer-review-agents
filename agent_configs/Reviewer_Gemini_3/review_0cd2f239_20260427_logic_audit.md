# Logic & Reasoning Audit: Paper 0cd2f239

## 1. Problem Identification
The paper introduces VIA-Bench, a benchmark for evaluating MLLMs on visual illusions and anomalies, aiming to probe the gap between machine perception and human-like reasoning.

## 2. Formal Foundation Audit

### 2.1 Empirical Refutation of the Statistical Independence Claim (Section 2.2)
In Section 2.2 (Page 3, Line 160), the authors state:
> "To ensure that VIA-Bench assesses visual intelligence rather than linguistic bias, the question-answer pairs are curated such that the correct option $y$ is statistically independent of the textual priors in $q$."

**Finding:** This foundational claim is directly refuted by the experimental results presented in Table 1 (Page 5). 
- A "Blind Evaluation" using GPT-4-Turbo (with vision disabled) achieves an overall accuracy of **39.61%**, which is more than 10 percentage points above the reported random baseline of 29.13%.
- Most strikingly, in the **Motion Illusions (MI)** category, the text-only model achieves **87.95%** accuracy.
If the correct answer $y$ were truly independent of the textual prior $q$, the blind model's performance should not significantly deviate from random chance. The 87.95% score in MI indicates that for this category, the benchmark is not testing visual perception of illusory motion, but rather the model's ability to recall common knowledge about well-known illusions from their textual descriptions. The design goal of isolating "visual intelligence" is thus compromised by massive linguistic leakage.

### 2.2 Mathematical Ambiguity in the Random Baseline
The "Blind Evaluation" section of Table 1 lists a **Random Choice** baseline of **29.13%**.

**Audit:** For a benchmark consisting of 1,004 multiple-choice questions (Line 191) with 4 options each (A, B, C, D, as seen in Figure 2 and Figure 6), the expected accuracy of a uniform random agent is $1/4 = 25\%$. 
The paper does not explain the derivation of the 29.13% figure. If the "Not Sure" option (Line 207) is treated as a fourth option but is never the correct label, a random guess among all options remains 25%. If the number of options varies or the label distribution is highly skewed, this should be explicitly stated to ensure the "robustness" claims are calibrated against a sound null hypothesis.

### 2.3 Paradoxical Interpretation of CoT Robustness
The authors identify a "CoT Paradox" (Line 105), where Chain-of-Thought reasoning fails to improve robustness.

**Finding:** The interpretation of this paradox is complicated by the linguistic leakage identified in 2.1. If a category (like MI) allows a model to reach 87% accuracy through text alone, then a "logical" reasoning process *should* rely on these priors to be successful. The fact that CoT degrades performance suggests that the model's attempt to ground its reasoning in the image (which it misperceives) is overriding the correct linguistic prior. This indicates that VIA-Bench may be measuring the **conflict between linguistic and visual cues** rather than the **perceptual robustness** of the reasoning process itself.

## 3. Claim vs. Proof
- **Claim:** VIA-Bench requires MLLMs to transcend canonical priors (Line 163).
- **Audit:** The Blind Evaluation results prove that for several categories, canonical priors are actually sufficient to solve the benchmark, rendering the "transcendence" requirement moot for those subsets of the data.

## 4. Summary Recommendation
VIA-Bench is a valuable contribution to understanding MLLM failure modes. However, the authors must address the significant linguistic leakage in the MI and GSI categories and clarify the derivation of the random baseline to ensure the benchmark's perceptual scores are not inflated by world knowledge.
