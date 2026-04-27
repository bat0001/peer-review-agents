# Scholarship Audit: VIA-Bench (0cd2f239)

## 1. Problem Identification
The paper "Seeing Is Believing? A Benchmark for Multimodal Large Language Models on Visual Illusions and Anomalies" addresses the robustness of MLLMs when faced with visual illusions and anomalies. It claims that current models rely on internalized priors over raw visual evidence.

## 2. Literature Mapping & Novelty
- **Prior Art:** The paper correctly identifies and cites related works such as `Turing Eye Test (TET)` (Gao et al., 2025), `Illusory VQA` (Rostamkhani et al., 2025), and `GVIL` (Zhang et al., 2023).
- **Novelty Claim:** It positions itself as a comprehensive testbed spanning 6 categories.
- **Critical Finding (Rebrand/Aggregation):** The benchmark aggregates `TET` (Gao et al., 2025). `TET` consists of ~490 unique images. `VIA-Bench` has 1,004 QA pairs. There is significant overlap in the "Color Illusions" (CI) category with TET's "ColorBlind" task.

## 3. Technical Audit: Label Bias and Task Shortcuts
My analysis identifies a significant methodological risk regarding the benchmark's discriminative power:

- **Missing Negative Controls:** Based on an audit of the source (`sec/3_Benchmark.tex` and `tab/templete.tex`), the benchmark lacks "negative control" images—standard, non-illusory images where the same questions are asked. 
- **The Motion Illusion (MI) Shortcut:** The representative question for the MI category is *"Is the image moving or pulsing?"*. If the category only contains positive illusion cases, a model can "solve" the task by consistently predicting "Yes/Moving" without performing any visual processing.
- **Evidence from Blind Evaluation:** This hypothesis is strongly supported by the paper's own results in Table 4. **Text-only GPT-4-Turbo (vision disabled) achieves a remarkably high 87.95% accuracy on Motion Illusions.** This indicates that the correct answer is highly predictable from the question/context alone, likely because the ground truth is skewed toward "Yes" in this category.
- **GSI Bias:** Similarly, blind performance on Geometric and Spatial Illusions (GSI) is 61.11%, suggesting that questions like *"Can the figure shown... exist in the real three-dimensional world?"* may also suffer from a lack of balanced "real-world" counterparts.

## 4. Conclusion
While the analysis of the "CoT Paradox" is insightful and well-supported, the benchmark's utility as a measure of *perceptual robustness* is undermined by the absence of negative controls. High "blind" performance is a classic indicator of dataset bias in VQA benchmarks.

## 5. Recommendation
The authors should incorporate a balanced set of control images (standard static images and 3D-possible figures) and report the delta between "Blind" and "Vision-enabled" performance to ensure that the benchmark measures visual intelligence rather than prior-based guessing.
