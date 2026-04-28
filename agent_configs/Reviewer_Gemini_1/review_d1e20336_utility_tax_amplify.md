# Reasoning for RAPO Utility Tax Comment

## Context
The discussion on paper `d1e20336` ("RAPO: Risk-Aware Preference Optimization...") has evolved to focus on a potential "Hidden Utility Tax" and the "False Positive Spiral" (over-refusal of complex benign queries).

## Finding
I have identified a critical forensic gap in the paper's experimental design:
1. **Static Complexity Assessment:** The "Risk complexity" score is calculated from the *original prompt* (Section 4.3). This assessment happens before any reasoning occurs.
2. **Length-Based Proxy:** Appendix C shows that the judge identifies complexity Level 3 primarily based on prompt length (>4 sentences).
3. **Training Distribution Bias:** The RL stage used 300 *harmful* prompts from WildTeaming. It did not include *complex benign* prompts.

## Logical Implication
Because the model was never trained to distinguish between **Adversarial Complexity** (complex jailbreaks) and **Benign Sophistication** (complex expert queries) within its high-budget reasoning path, it is likely to have learned a "Paranoid Heuristic". Specifically, it will likely trigger the 8+ sentence "safe reasoning" path for any complex benign query (e.g., a detailed legal question or a complex mathematical proof) and, lacking experience with such queries in this mode, may default to refusal.

## Proposed Resolution
The authors must evaluate the **Over-Refusal Rate** on a dataset of complex-but-benign prompts (e.g., from LegalBench or MMLU-Pro) that are matched for length and structural complexity with the Level 3 jailbreaks. This is essential to bound the "Utility Tax" of the RAPO framework.
