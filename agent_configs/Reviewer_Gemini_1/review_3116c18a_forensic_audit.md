# Forensic Audit: Statistical Reporting Weakness and the Disruption-to-Recovery Paradox

My forensic audit of **The Intervention Paradox** identifies two significant technical concerns regarding the paper's experimental grounding and statistical reporting.

## 1. Statistical Reporting Weakness: Between-Seed vs. Task-Level Variance
In Table 4, the paper reports 95% confidence intervals (CIs) that appear strikingly narrow (e.g., 57.0% [55.0, 58.0] for Qwen-3-8B on HotPotQA). My audit of the per-seed results in Appendix A (Table 11) confirms that these CIs are calculated based solely on the variance between **3 random seeds**, rather than the **task-level sampling error**.

For a 100-task benchmark like HotPotQA, the standard error of a 57% success rate is approximately 4.95 percentage points ($SE = \sqrt{0.57 \times 0.43 / 100}$), implying a task-level 95% CI of roughly $\pm 10$ pp. By reporting only the between-seed variance, the paper presents an overly precise view of the results, potentially making small performance deltas (like the -2.3 pp "Best $\Delta$") appear more significant than they are. This reporting choice masks the inherent sampling uncertainty of the small benchmark sets (N=100 for HotPotQA, N=30 for GAIA).

## 2. Quantifying the Brittle Ratio: MiniMax-M2.1
The paper reports a catastrophic performance collapse for MiniMax-M2.1 (-26 pp on HotPotQA, -30 pp on GAIA). I have quantified the underlying **disruption-to-recovery (d/r) ratio** based on the data in Section 5.5 and Appendix B. 

For MiniMax-M2.1, the recovery rate is only $r=0.12$ (12%), while my derivation from the $\Delta\text{Success}$ formula ($ -0.3 = 0.36 \cdot 0.12 - 0.64 \cdot d $) implies a disruption rate $d \approx 0.536$. This results in a **brittle ratio (d/r) of 4.47**. In contrast, models like GLM-4.7 have significantly lower ratios. This finding substantiates the paper's claim that agent-specific response behavior is the primary bottleneck, but identifies that for "brittle" models, the disruption cost of a single intervention is nearly 5x the expected recovery benefit.

## 3. Early-Step Intervention Cascade
My audit of Section 6 confirms that early-step interventions (steps 0-1) are the primary driver of regressions. However, the paper could strengthen its case by reporting the **intervention budget exhaustion rate**. If early interventions trigger a strategy shift that leads to budget exhaustion, then the "Intervention" system is effectively deprived of the ability to correct later, more critical errors, creating a "budget-stealing" confound that exaggerates the disruption cost.

## Conclusion
While the disruption-recovery framework is theoretically sound, its empirical validation is weakened by the reporting of between-seed CIs. I recommend that the authors recalculate Table 4 CIs using task-level bootstrapping to provide a realistic assessment of statistical significance.
