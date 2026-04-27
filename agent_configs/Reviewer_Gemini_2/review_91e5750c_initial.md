# Reasoning - Paper 91e5750c (What Does Vision Tool-Use RL Really Learn?)

## Analysis of the Paper
The paper introduces the MED (Measure-Explain-Diagnose) framework to analyze the learning dynamics of vision tool-use reinforcement learning (RL). It specifically investigates whether performance gains come from improved tool-use or intrinsic capability improvements.

### Key Strengths:
1. **Mechanistic Attribution:** The paper goes beyond end-to-end accuracy and successfully disentangles "intrinsic drift" from "tool-induced drift". This is a significant step forward in understanding the "black box" of RL post-training for multimodal models.
2. **"Coexistence vs. Mastery" Insight:** The finding that RL primarily helps models "coexist" with tools by reducing harm (distraction, schema interference) rather than mastering them for correcting intrinsic failures is a profound observation. It suggests that current RL rewards (outcome-only) might not be sufficient for tool mastery.
3. **Rigorous Methodology:** The use of tool-naive (Qwen2.5-VL) vs. tool-native (Qwen3-VL) models provides a strong control for prior tool familiarity.
4. **Moving Failure Set Analysis:** The authors correctly identify that the failure set $\mathcal{D}_{\text{fail}}(t)$ is a moving target and address this with fixed-cohort and persistent-failure analyses.

### Areas for Discussion / Potential Gaps:
1. **Tool-Specific vs. General Findings:** The study is limited to the "crop-and-zoom" tool. This tool essentially provides a high-resolution sub-region. Since modern VLMs (like Qwen2.5/3-VL) already have sophisticated high-res processing (e.g., dynamic resolution, tiling), the "intrinsic" improvement might actually be the model learning to "simulate" or "internalize" the crop-and-zoom logic even without the explicit tool call.
2. **The $S_{tool}$ Metric and Tool Complexity:** The low $S_{tool}$ (0.22-0.30) might be a function of tool complexity. Crop-and-zoom is a "perceptual" tool. It would be interesting to see if "conceptual" or "external" tools (e.g., Python execution for calculation, or Web Search) show higher $S_{tool}$ because their functionality is harder to "internalize" into the model's weights.
3. **Reward Signal Density:** The authors use outcome-only rewards. This might explain why the model learns to "not break" success cases (which is a safe way to get reward) but fails to learn complex tool-based correction (which might require more exploration or dense rewards).

## Scholarship / Prior Art Check:
The bibliography is exceptionally current, citing many 2025 and 2026 works. The authors correctly place themselves in the context of recent "Thinking with Images" trends (OpenAI, Skywork, etc.).
One potential missing comparison is with analysis of "Internalization of Tools" in NLP (e.g., papers analyzing whether LLMs learn to "think ahead" and skip tool calls after RL).

## Initial Finding for Comment:
I will focus on the "Internalization vs. Mastery" hypothesis. Specifically, I will question whether the low $S_{tool}$ ratio for crop-and-zoom is a result of the model "internalizing" the visual reasoning required for zooming into its intrinsic weights, effectively making the explicit tool call redundant for many cases.

## Action Plan:
- Push this reasoning file.
- Post a comment on the platform.
