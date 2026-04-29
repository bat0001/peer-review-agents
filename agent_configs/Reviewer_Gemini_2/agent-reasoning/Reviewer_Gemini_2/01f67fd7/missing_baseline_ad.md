# Reasoning for Missing Baseline (Algorithm Distillation) on Paper 01f67fd7

## Finding
The paper "Learning in Context, Guided by Choice: A Reward-Free Paradigm for Reinforcement Learning with Transformers" (ICPRL) identifies a novel "reward-free" ICRL paradigm but fails to compare against the canonical In-Context Reinforcement Learning (ICRL) baseline: **Algorithm Distillation (AD)** (Laskin et al., NeurIPS 2022).

## Context
ICPRL claims to be a "new learning paradigm" that eliminates the need for reward supervision. While it compares against **Decision Pretrained Transformer (DPT)** (Lee et al., 2023/2024), it omits a head-to-head comparison with Algorithm Distillation. AD is fundamentally relevant because it demonstrates how a transformer can distill the learning process of an RL algorithm into its weights, enabling in-context policy improvement. 

## Reasoning
1. **Canonical Status**: Algorithm Distillation is widely recognized as the first work to demonstrate that sequential modeling can capture RL learning dynamics. Any claim to a "new paradigm" in ICRL must be measured against the performance and efficiency of AD.
2. **Reward-Free Applicability**: While AD is often trained on trajectories from a reward-seeking algorithm, the resulting transformer policy at test time operates purely on the (s, a) history to improve behavior. Comparing ICPRL's ICPO/ICRG methods against an AD-trained transformer would clarify whether the preference-based objective provides a more efficient distillation of task structure than simple sequential modeling of an RL algorithm's progress.
3. **Scholarship Gap**: The paper cites AD in the related work (Section 2, lines 258-261) but excludes it from the experimental suite (Section 7). This prevents the community from understanding the trade-offs between "distilling an algorithm" (AD) and "distilling a preference-aligned policy" (ICPRL).

## Evidence
- **Laskin, M., et al. (2022). "In-context Reinforcement Learning with Algorithm Distillation." NeurIPS.** arXiv:2210.14215.
- The ICPRL paper's experiments only include DPT and a Behavioral Cloning (BC) baseline.

## Proposed Action
Add a comparison against Algorithm Distillation (AD) on the DarkRoom and Meta-World benchmarks to validate the efficiency of the preference-based paradigm against the established ICRL state-of-the-art.
