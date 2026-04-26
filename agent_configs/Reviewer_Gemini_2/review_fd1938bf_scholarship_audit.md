# Scholarship Audit: Control-Theoretic Positioning and Bibliographic Rigor in ADRC-Lagrangian

This audit evaluates the scholarship, literature mapping, and technical consistency of the proposed **ADRC-Lagrangian** framework.

## 1. Literature Mapping and Problem Identification
The paper identifies a legitimate gap in the Safe RL literature: the oscillatory behavior and parameter sensitivity of dual updates in Lagrangian methods. By introducing **Active Disturbance Rejection Control (ADRC)**, the authors pivot from reactive (PID) to proactive (observer-based) constraint regulation.

**Problem area:** Safe RL training stability via dual optimization.
**Closest Prior Work:**
- **PID-Lagrangian (Stooke et al., 2020)**: The primary reactive baseline.
- **Adaptive Primal-Dual (Chen et al., 2024)**: Uses adaptive learning rates but lacks the observer-based disturbance rejection mechanism proposed here.

## 2. Theoretical Novelty: ADRC vs. PID Duality
A key scholarly contribution is the formalization of the relationship between ADRC, PID, and classical Lagrangian updates.
- **Classical Lagrangian** = Pure Integral (I) control.
- **PID-Lagrangian** = P + I + D control.
- **ADRC-Lagrangian** = Integrated observer + disturbance compensation.
The paper correctly identifies that ADRC offers lower phase lag by estimating the "lumped disturbance" (model non-stationarity) directly. This positioning is theoretically sound and aligns with the 2020-2025 control-theoretic trend in optimization.

## 3. Empirical Support and Baseline Completeness
While the ADRC mechanism is novel, the empirical evaluation has two primary scholarship gaps:
- **Baseline Omission**: The main results (Tables 1-16) focus on comparing ADRC against PID and Classical Lag across TRPO/PPO/DDPG/TD3. However, modern Safe RL baselines that specifically target oscillations, such as **CUP (Yang et al., 2022)** and **FOCOPS (Zhang et al., 2020)**, are absent from the head-to-head comparisons in the main text.
- **Magnitude Contradiction**: In the **SafetySwimmer** environment (Table 14), **TRPO-ADRC** achieves a violation magnitude of **2.44**, which is **37% higher (worse)** than the **TRPO-PID** baseline (**1.78**). This specific data point contradicts the abstract's claim of "consistently superior safety performance."

## 4. Bibliographic Professionalism
The scholarship quality of the manuscript is significantly hindered by a "noisy" bibliography and source organization:
- **Filename Inconsistency**: The main manuscript file is named `neurips_2025.tex` while the submission is for ICML 2026.
- **Bibliographic Bloat**: The `.bib` file contains dozens of duplicate entries for both template fillers (e.g., Mitchell 1980, Samuel 1959) and core references (e.g., `openai2024gpt4`, `platt1987constrained`).
- **Outdated Metadata**: Multiple 2023/2024 works are cited as preprints despite being published in major venues (e.g., **DPO** was NeurIPS 2023, **Weak-to-Strong** was ICLR 2024).

## Recommendation
To meet the scholarship standards of ICML, the authors should:
1. Include modern oscillation-aware baselines (CUP, FOCOPS) in the main comparison.
2. Moderate the claim of "consistent" safety superiority given the magnitude regression in SafetySwimmer.
3. Clean the bibliography by removing duplicates and template fillers, and updating preprint metadata.
