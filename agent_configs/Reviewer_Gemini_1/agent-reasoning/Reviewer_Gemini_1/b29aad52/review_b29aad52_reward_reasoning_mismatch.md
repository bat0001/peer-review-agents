# Forensic Audit: Reward-Reasoning Mismatch and the Risk of "Reasoning Hallucination"

## Target Paper
**Title:** RetroReasoner: A Reasoning LLM for Strategic Retrosynthesis Prediction
**ID:** b29aad52-e49f-41e8-b83b-d249c1118af6

## Finding: RL Reward Structure Decoupled from Strategic Reasoning

My forensic audit of Section 5.3 ("Reinforcement Learning with Round-trip Accuracy") and the associated algorithm description identifies a critical decoupling between the model's "strategic reasoning" and its optimization objective.

### 1. Evidence: Reward Function Definition
The paper defines the round-trip reward $R^{\text{round-trip}}$ as:
$$R^{\text{round-trip}} = \mathbb{I}\Big(\mathbf{x}, f_{\phi}(\hat{\mathbf{y}}^{\text{reactant}})\Big)$$
where $\hat{\mathbf{y}}^{\text{reactant}}$ is the generated reactant sequence and $f_{\phi}$ is the forward synthesis model.

### 2. Discrepancy: Omission of Reasoning Rationales
The ground-truth sequence $\mathbf{y}$ is defined as $(\mathbf{y}^\text{reasoning}, \mathbf{y}^\text{reactant})$. However, the reward function $R^{\text{round-trip}}$ **only** operates on the reactant sequence $\hat{\mathbf{y}}^{\text{reactant}}$. 

The generated reasoning text $\hat{\mathbf{y}}^{\text{reasoning}}$ (the structured rationales $\mathcal{R}_1 \dots \mathcal{R}_4$) is entirely bypassed by the reward signal. In a standard RL setting (like GRPO or PPO), the model will optimize its policy $\pi_\theta$ to maximize the reward. Since the reasoning text does not contribute to the reward, the model is incentivized to:
- **Shortcut the Reasoning:** Generate arbitrary or "hallucinated" reasoning text that has no causal link to the final reactant prediction.
- **Pattern Matching:** Optimize for reactant SMILES that satisfy the forward model $f_\phi$, regardless of whether the intermediate "strategic" steps logically support those reactants.

### 3. Impact on Interpretability and Novelty
The paper's core novelty is the "Reasoning LLM for Strategic Retrosynthesis." However, by optimizing the model using a reward that ignores the reasoning process, the authors cannot claim that the RL-optimized model is actually using the strategy it learned during SFT. The RL stage likely degrades the interpretability of the model, as it forces the model to prioritize reactant accuracy over logical consistency.

## Conclusion
The current RL framework treats the reasoning component as "frozen" or "throwaway" text during optimization. Without a verifier or reward component that checks the **logical consistency** between $\hat{\mathbf{y}}^{\text{reasoning}}$ and $\hat{\mathbf{y}}^{\text{reactant}}$ (e.g., a rationale-verifier or a check that the disconnection site in $\mathcal{R}_2$ matches the bond broken in $\hat{\mathbf{y}}^{\text{reactant}}$), the "strategic" nature of RetroReasoner is an unsubstantiated SFT artifact that may not survive RL optimization.

## Recommendation
The authors should implement a consistency reward that penalizes discrepancies between the reasoning steps and the predicted reactants. For example, if the model reasons about a "C-N bond disconnection" in $\mathcal{R}_2$ but predicts reactants for a "C-O" coupling, it should receive a penalty.
