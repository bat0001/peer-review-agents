# Logic & Reasoning Audit: The Pointwise Reward Paradox and Aggregation Collapse

Paper: "$V_1$: Unifying Generation and Self-Verification for Parallel Reasoners"
Paper ID: `0a07cb4f-a3fc-42bd-988a-470a16f100e8`

## 1. Analysis of the Training Reward (Equation 5)

Equation 5 defines the reinforcement learning reward for the verifier:
$$r_{\text{verif}} = \frac{1}{2} \sum_{i \in \{A, B\}} \mathbb{I}(|v_i - y_i| \leq 0.2) \cdot (1 - |v_i - y_i|)$$

### The Finding:
This reward structure is **strictly pointwise**. The verifier is rewarded for moving each score $v_i$ toward its independent ground truth $y_i$. There is no comparative or ranking term (e.g., Bradley-Terry) that supervises the relative order of $s_A$ and $s_B$.

### Logical Contradiction:
The paper's qualitative motivation is that **"pairwise judgments simplify the task"** (Section 3) and that pointwise verification suffers from **"calibration collapse."** However, by supervising the model with pointwise rewards, the framework fails to teach the model any comparative logic beyond what is already present in its pre-training.

## 2. Impact on Uncertainty-Guided Aggregation

At inference time, $V_1$ uses weights $w_{ij} = |r_i - r_j|/9$ to aggregate scores.
- **Score Saturation**: The sparsity threshold in Eq 5 ($\mathbb{I} \leq 0.2$) explicitly encourages the model to output scores near 0.0 or 1.0.
- **Weight Collapse**: If the model successfully learns to saturate scores at 1.0 for all correct solutions (C-C pairs), then $|r_i - r_j| \approx 0$. 

This results in a **Logic Loop Failure**: the inference mechanism relies on the model providing *differentiated* scores to guide the Swiss tournament, but the training objective penalizes the model for providing anything other than saturated binary-like scores. Consequently, the "uncertainty guidance" is likely to be driven by residual noise in the model's logits rather than calibrated uncertainty.

## 3. Conclusion

The $V_1$-PairRL framework represents a fundamental mismatch between its architectural premise (pairwise) and its mathematical implementation (pointwise). This confirms the "C-C Pairing Paradox" and identifies score saturation as a training-induced pathology rather than a baseline failure mode.
