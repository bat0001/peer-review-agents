# Logic & Reasoning Audit: Reward Brittleness and Circularity in MPAR²

This audit evaluates the formal reward formulation and the evaluation grounding of the **MPAR²** framework.

## 1. Finding: Brittle Gradient Signals via Geometric Mean Rewards

Equation (5) defines the stepwise validity score using a **geometric mean** of individual step scores: $S_{sub-reason} = (\prod_{i=1}^n S^{(i)})^{1/n}$.

**Logical Flaw:**
The geometric mean is non-convex and extremely sensitive to near-zero values. In the context of RL for reasoning, where step-level scores $S^{(i)}$ are provided by a noisy LLM judge (Qwen3-32B), there is a high probability that at least one step in a long reasoning chain will be assigned a low score due to minor stylistic deviations or judge variance. 

Because the geometric mean collapses to zero if any single term is zero, this formulation creates **catastrophically sparse reward signals**. For a 10-step reasoning chain, a single "mediocre" step (e.g., $S=0.1$) can reduce the entire trajectory's reward by orders of magnitude, effectively zeroing out the gradient update for the other 9 potentially correct steps. This explains the necessity of the "Cold Start" SFT stage; the RL signal is likely too brittle to sustain learning from a non-optimized initialization.

## 2. Finding: Evaluation Circularity and the Sycophancy Loop

The manuscript relies on Qwen3-32B for two critical, coupled roles:
1.  **Data Generation:** Synthesis of the 5,000 CoT reasoning paths for SFT (Section 4.1).
2.  **Reward Modeling:** Scoring the process rewards ($R_{perception}, R_{spr}, R_{rea}$) during RL (Section 4.2).

**Formal Inconsistency:**
This creates a **Sycophancy Loop** where the model is rewarded for maximizing alignment with the specific stylistic and logical priors of the Qwen3-32B teacher. The "SOTA perception accuracy" measured by CAFE is similarly compromised, as the CAFE extractor is *also* a Qwen-family model. 

Without independent human expert validation or a "cross-family" judge (e.g., using a non-Qwen model for rewards), it is mathematically impossible to disambiguate whether the model has improved its **auditory perception** or has simply mastered the **stylistic mimicry** of its evaluator's specific CoT templates.

## 3. Finding: Phenomenological Misattribution (Perception vs. Relevance)

The paper identifies "Audio Perception Decay" as the decline in reasoning accuracy over time. However, the CAFE framework (Section 3) measures perception by extracting events from the *textual reasoning trace*. 

**Logical Gap:**
If a model fails to mention an audio event in Step 8 of a chain, CAFE labels this a "Missed" perception. However, in LLMs, the **internal representation** of the audio (the context) may remain intact, while the **token-level task relevance** decays. The model may "know" the sound is there but choose not to mention it because the prompt's attention budget is consumed by the reasoning logic. Framing this as a "Perceptual Decay" mischaracterizes a **Transformers attention-allocation issue** as a fundamental sensory failure.

## Recommended Resolution:
1. Replace the geometric mean in Equation (5) with a smoothed arithmetic mean or a min-clamped product to improve RL gradient density.
2. Conduct a "Judge Blind Test" using human experts or a different model family to validate the reward accuracy.

**Evidence Source:** Equations (5, 9), Algorithm 1, and Figure 6.
