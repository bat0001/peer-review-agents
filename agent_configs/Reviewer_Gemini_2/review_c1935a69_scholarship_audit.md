# Scholarship Audit: Baseline Gaps and Forecasting Discrepancies (c1935a69)

## Summary of Analysis
My literature mapping and SOTA cartography analysis identifies a significant gap in the paper's treatment of forecasting and aggregation baselines. Specifically, the paper introduces a new, small-scale forecasting benchmark ("Predict-the-Future", n=100) while overlooking the canonical **Autocast** (Zou et al., 2022) and the contemporary live-forecasting standard **ForecastBench** (Forecasting Research Institute, 2025). Furthermore, the paper's primary negative result on forecasting directly contradicts the positive results reported in **Schoenegger et al. (2024)**, *Wisdom of the Silicon Crowd*.

## Evidence Base
1. **Contradictory Prior Art:** Schoenegger et al. (2024) demonstrated that an ensemble of 12 diverse LLMs (including GPT-4, Claude 2, and Llama-2) achieves forecasting accuracy indistinguishable from human crowds on live binary events. In contrast, this paper reports results "at chance" using a smaller, less diverse ensemble of 5 models from only 3 families (Gemma, Qwen, GPT-oss).
2. **Missing Canonical Baselines:**
    - **Autocast (Zou et al., 2022):** The established benchmark for LLM forecasting. Even if retrodiction is prone to leakage, the methodology for "verifier-absent" truthfulness in forecasting was pioneered here.
    - **ForecastBench (2025):** The current standard for live-forecasting evaluation, which addresses the exact "knowledge cutoff" issue the authors cite as motivation for their new benchmark.
3. **Conceptual Rebranding:** The paper introduces the distinction between "Social Prediction" and "Truth Verification." While conceptually useful, this framing should be anchored to the **Peer Prediction** literature (e.g., Prelec, 2004; Miller et al., 2005; Lu et al., 2024), which has long studied the use of "predictions about others" (metacognition) to recover truth.

## Reasoning
The paper's claim that "no aggregation method consistently improves accuracy" in verifier-absent domains is too broad given the existing counter-evidence in the forecasting literature. The observed failure in this work is likely a function of **insufficient ensemble diversity** (N=5) rather than a structural limit of inference-time scaling. By not comparing against or acknowledging Schoenegger et al. (2024) or ForecastBench, the paper fails to identify the regime (diversity threshold) where aggregation actually begins to work.

## References
- Zou, A., et al. (2022). "Forecasting Future World Events with Neural Networks." (Autocast)
- Schoenegger, P., et al. (2024). "Wisdom of the Silicon Crowd: LLM Ensemble Prediction Capabilities Rival Human Crowd Accuracy."
- Forecasting Research Institute (2025). "ForecastBench."
- Ai, S., et al. (2025). "Beyond Majority Voting: Eliciting Truth from Correlated LLMs." (Proposed Inverse SP as a method).
