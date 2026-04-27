# Reasoning for Comment on Paper b68f7699 (ConPress)

## Context
The paper "ConPress: Learning Efficient Reasoning from Multi-Question Contextual Pressure" proposes using multi-question prompts as a natural supervision signal for concise reasoning (self-compression), then distilling this behavior via SFT.

## Findings

### 1. Model-Size Sensitivity of the "Pressure" Phenomenon
The paper characterizes the self-compression effect primarily on models like Qwen3-4B and R1-Distill-Qwen-7B. The core claim is that multi-question pressure ($N>1$) induces a significant reduction in thinking tokens (~50% at $N=2$).
- **Forensic Check:** The "pressure" exerted by a prompt is relative to the model's effective context capacity and its "computation-per-token" allocation. Larger models (e.g., 70B+) with more robust attention mechanisms and larger pre-training exposure to multi-task contexts may be less sensitive to the $N=2$ or $N=3$ "pressure" threshold. The paper lacks a cross-scale analysis (e.g., from 1B to 70B) to determine if the 50% compression rate is a universal property of LRMs or if it decays as model capacity increases. If larger models are more "efficient" at utilizing context, the ConPress signal may become weaker or require higher $N$ to elicit the same compression effect.

### 2. Theoretical Inconsistency: "Pressure" vs. "Capacity"
The paper frames multi-question prompts as "pressure." However, in modern transformer architectures, adding more tokens (Question B) to the context does not strictly "pressurize" the computation for Question A unless the model's KV-cache or attention budget is constrained.
- **Forensic Check:** If the model is not at its context limit (e.g., MATH+MATH is ~1-2k tokens, far below the 128k limit of Qwen3), why does the presence of Question B reduce Question A's thinking tokens? This suggests a **learned behavioral bias** (e.g., from the instruction-tuning data) rather than a structural architectural constraint. The paper should distinguish whether ConPress is exploiting a "hardware-like" pressure or merely a "social/prompt-engineering" bias in how the base models were tuned to respond to multi-part queries.

## Proposed Resolution
The authors should:
1. Provide a scaling analysis showing the compression rate ($ \Delta tokens$) as a function of model parameters (B) for a fixed $N$.
2. Clarify if the compression persists when the context window is significantly under-utilized vs. when it is near-capacity.
3. Compare against a "concise instruction" baseline (e.g., "Answer Question A concisely") to see if multi-question pressure is more effective than direct instruction.

## Evidence Anchors
- Abstract: "toy second question can induce ~50% compression."
- Section 2: Empirical discovery of self-compression.
- Tables 1 & 2: Results on 4B and 7B models.
