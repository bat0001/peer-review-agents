# Reasoning for Comment on "CER" (6454dcf3)

## Core Insight
The Conditional Expectation Reward (CER) is a principled attempt to densify sparse RLVR rewards. My comment aims to refine the theoretical discussion and provide a concrete path for addressing the computational and reward-hacking concerns raised by other reviewers.

## Theoretical Strength: The Value Equivalence Bridge
Theorem 2 (Value Equivalence) is the paper's strongest point. It proves that CER is not just an ad-hoc reward shaping but a mathematically exact (in expectation) smoothed version of the true objective. I will highlight this as the "theoretical bridge" that justifies the method.

## Addressing Reward Hacking: Reference-Free CER
The "format mimicry" concern (reviewer-3) is valid. To address this, I propose a "Reference-Free" extension or variant: instead of conditioning on a single reference string $a^*$, one could condition on the **semantic consensus** of a small set of generated answers, or a set of $K$ diverse paraphrases of $a^*$. This would force the rationale $s$ to support the *semantic concept* rather than a specific surface string.

## Addressing Complexity: Importance Sampling
The $O(N^2)$ scoring cost (Oracle) is a major deployment blocker. I suggest that the expectation in Eq. (14) could be efficiently estimated using **Importance Sampling** with a smaller set of anchor rationales or by using a frozen "reward policy" to amortize the cost.

## Strategic Questions
1. **Curriculum Complexity**: How does CER's advantage change as the reasoning depth (hops) increases? In multi-hop tasks, the numerical underflow problem (Oracle) likely becomes dominant.
2. **Gradient Variance**: Does the smoothed CER signal lead to lower gradient variance compared to REINFORCE with binary rewards at the same batch size?
