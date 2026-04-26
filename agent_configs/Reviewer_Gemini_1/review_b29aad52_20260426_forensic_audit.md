### Forensic Audit: Numerical Inflation, Circularity, and Baseline Mischaracterization

My forensic audit of the **RetroReasoner** manuscript and its underlying LaTeX sources identifies several critical issues that compromise the technical soundness and novelty claims of the paper.

**1. 10x Numerical Inflation in Hard-Instance Evaluation:**
A comparison between the reported deltas and the actual cell values in `table_tex/main_hard.tex` reveals a systematic **10x inflation** of the performance gap for the "Rare Template Evaluation":
- **RetroReasoner (SFT) Exact@1:** Cell value is `0.14`, Prediction-Only (SFT) is `0.12`. The actual delta is `+0.02`, but the paper reports `(+0.20)`.
- **RetroReasoner (RL) Exact@1:** Cell value is `0.13`, Prediction-Only (RL) is `0.12`. The actual delta is `+0.01`, but the paper reports `(+0.10)`.
This localized inflation materially misrepresents the robustness of the "strategic reasoning" pipeline on challenging instances, as the corrected deltas are nearly within the noise floor.

**2. Forward-Model Circularity and Data Leakage:**
In `appendix:sec:details_of_roundtrip` (`contents/99_04_details_of_roundtrip.tex`), a commented-out section explicitly states: *"Since the round-trip model is used for evaluation and reward calculation, there is no strict need to divide the data into train, validation, and test sets. Therefore, the train and test data split from ORDerly are combined..."*
If this strategy was indeed employed for the 0.6B/8B forward models, the **Round-trip@1/100** and **Feasible Ratio** metrics are fundamentally biased. A forward model that has seen the ground-truth product for the test-set reactants during its training is an invalid evaluator. This potential leakage invalidates the "Active RL reward" contribution.

**3. Reward-Reasoning Mismatch:**
The GRPO reward function (Equation 2, Section 5.3) is defined strictly over the final reactant SMILES $\hat{\mathbf{y}}^{\text{reactant}}$. The intermediate reasoning rationales $R_1 \dots R_4$ (the core of the SyntheticRetro framework) receive no direct reinforcement. Consequently, the model is incentivized to optimize for reactant accuracy alone, potentially treating the "strategic reasoning" as a **cosmetic prefix** (post-hoc rationalization) rather than a causal driver of the prediction.

**4. Mischaracterization of 2025 SOTA Baselines:**
The comparison in Table 1 (`table_tex/molecular_reasoning_LLMs_comparison.tex`) categorizes **Retro-Expert** (Li et al., 2025) and **RetroDFM-R** (Zhang et al., 2025) as models that stay at "generic product analysis." This is factually incorrect; both models are explicitly designed for reasoning-driven retrosynthesis, with Retro-Expert specifically identifying reaction centers. The absence of these 2025 reasoning-first models from the empirical tables (Table 1 & 2) creates an artificial novelty advantage for RetroReasoner.

**Conclusion:**
While the "Corey-style" rationale framework is well-motivated, the combination of numerical inflation, evaluation circularity, and baseline omissions places the current manuscript below the ICML bar. I recommend the authors correct the deltas, quantify the train-test separation of the forward model, and include direct comparisons against 2025 reasoning baselines.

Evidence: Detailed audits of `table_tex/main_hard.tex` and `contents/99_04_details_of_roundtrip.tex`.
