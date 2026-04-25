# Reasoning for Review of Paper 00efc394

## 1. Analysis of Causal Framework (Section 2.2)

The authors use a potential outcomes framework to define Token-Level Personalization Degree (PIR) as the Causal Effect (CE) of the persona $P$ on token $y_i$.

**Logical Flaw 1: SUTVA Violation in Autoregressive Models**
- Assumption 2.1 (No Interference / SUTVA) is claimed to hold. However, in autoregressive language models, the outcome at token $i$ ($y_i$) is explicitly dependent on the outcomes of previous tokens $y_{<i}$.
- If the persona $P$ is changed, it affects the entire joint distribution $P(y_1, \dots, y_n | P, X)$. 
- An intervention on the persona for token $j < i$ affects the potential outcome of token $i$ through the sequence history. This is a direct violation of SUTVA, which requires that the outcome for unit $i$ depends only on the treatment assigned to unit $i$.
- In LLMs, "units" (tokens) are not independent causal units; they are linked in a temporal chain.

**Logical Flaw 2: Mediation Bias (Direct vs. Total Effect)**
- The DAG in Figure 2 correctly identifies $X$ as a confounder. 
- However, it also shows $P \to Y_{<i} \to Y_i$. This means $Y_{<i}$ is a **mediator** for the effect of $P$ on $Y_i$.
- By conditioning on $y_{<i}$ (the reference prefix) in the CE calculation (Eq 380), the authors are measuring only the **Natural Direct Effect (NDE)** of the persona on the current token, blocking the **Indirect Effect** mediated by the previous tokens.
- In personalization, much of the "persona" signal is carried by the stylistic choices and naming conventions established in the prefix. By ignoring the mediated effect, PerContrast systematically under-estimates the importance of tokens that are part of a personalized "style" rather than a localized "fact."

## 2. Inconsistency in CE Formulation

- The CE is defined as $\log P(y_i | \text{Masked}) - \log P(y_i | \text{Non-Masked})$.
- If a token is *more* likely given the persona (Non-Masked), then $P(\text{Non-Masked}) > P(\text{Masked})$, leading to a **negative** CE.
- Usually, "personalization degree" should be positive for relevant tokens. The authors should clarify why they use this inverted sign or how it is handled in the PerCE loss (Section 3).

## 3. The "EM Perspective" Leap (Section 3)

- The authors frame PerCE as an Expectation-Maximization (EM) algorithm.
- However, in standard EM, the latent variable is usually a discrete class or a missing value. Here, the "latent" is a continuous personalization weight estimated by causal intervention.
- The mapping of this heuristic weighting to a formal EM convergence proof is likely tenuous and acts as "math-washing" for a simple adaptive upweighting scheme.
