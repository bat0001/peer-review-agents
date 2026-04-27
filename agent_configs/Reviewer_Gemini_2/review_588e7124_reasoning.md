# Scholarship Analysis - Paper 588e7124 (Under the Influence)

## Phase 1 - Literature Mapping

The paper correctly identifies and maps the 2024-2025 landscape of LLM social cognition:
- **Schoenegger et al. (2025a/b)** established the "superhuman" persuasiveness of LLMs in interactive contexts.
- **Wu et al. (2025)** introduced "rational vigilance" based on Bayesian source modeling.
- **Hu et al. (2025)** (LMGame-Bench) and **Todd et al. (2023)** established Sokoban as a benchmark for planning and reasoning.

The paper's claimed gap—the relationship between these capacities and task performance in sequential environments—is a valid and timely research question.

## Phase 2 - Finding: Vigilance Metric Artifacts vs. Cognitive Dissociation

The central claim that task performance and vigilance are "dissociable" (Section 4.2) rests on the lack of correlation between `µ_MA` and `ν_MA`. However, my analysis of the metric definition (Eq. 5) reveals a structural dependency:
1. `ν_MA` is only defined for "measurable" trials—those where the unassisted model would NOT have taken the advisor's desired action.
2. For high-performing models like **GPT-5** (100% solve rate, 89.9% optimality), the number of such trials for *benevolent* advice is near zero. This leads to the undefined ("--") entry in Table 1.
3. Conversely, for low-performing models like **Claude Sonnet 4**, nearly every trial is measurable.

This creates a **capability-stratification bias**: the vigilance score for high performers is based on a tiny, idiosyncratic sample of failure modes, while the score for low performers is based on their general behavior. The "dissociation" found (`p = .328`) likely reflects this measurement instability rather than a lack of underlying cognitive relationship.

## Phase 3 - Hidden Issue: Definition Drift from Persuasion to Compliance

While the paper uses the term "persuasion," the experimental setup measures **compliance** (the change in moves). In the broader SOTA map of social cognition (e.g., Cialdini & Goldstein 2004), persuasion typically requires an internal change in belief or attitude. By using a symbolic planner to generate the advice, the paper effectively tests **advice-following** under adversarial conditions. While this is highly relevant for AI safety (advisory roles), labeling it "persuasion" drifts from the established psychological definitions which usually involve linguistic influence on internal states.

## Recommendation for authors
To strengthen the dissociation claim, the authors should report vigilance metrics that are normalized by task difficulty or capability (e.g., comparing models only on the subset of puzzles where ALL models fail unassisted).
