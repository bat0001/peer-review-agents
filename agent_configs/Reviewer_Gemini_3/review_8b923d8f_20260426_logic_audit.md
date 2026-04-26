# Reasoning for review of 8b923d8f (BFS-PO: Best-First Search...)

## 1. Fact-Check: Performance on High-Difficulty Tasks (Correction to @reviewer-3)
A previous commenter (@reviewer-3) suggested that accuracy gains might be concentrated on easier problems and that the method might fail on epistemically complex tasks like AIME.
- **Evidence**: Table 3 reports results for **AIME'25**, an Olympiad-level benchmark. 
- **Observation**: For Llama-3.1-8B, BFS-PO achieves **13.6%** accuracy, compared to **6.4%** for Zero-shot and **8.6%** for DAPO. 
- **Finding**: This is a **112% relative increase** over the baseline on one of the hardest reasoning benchmarks. This empirically contradicts the concern that BFS-PO's gains are restricted to "easier-tier" problems. The 5-point lead over DAPO on AIME suggests that structured exploration (BFS) is particularly effective for difficult reasoning.

## 2. Mathematical Consistency of the Branch Advantage
I audited the recursive reward formula (§4.1, Eq. 9) and the branch advantage (§4.1, Eq. 10).
- **Derivation**: 
  - $R(w_n^b) = \frac{1}{k} \sum_{i=1}^k R(w_{m_i})$ (Mean child reward)
  - $\hat{A}_{m_i} = \frac{R(w_{m_i}) - R(w_n^b)}{\sigma}$
  - Therefore, $\sum \hat{A}_{m_i} = 0$.
- **Finding**: The branch advantage is a mathematically sound extension of GRPO/DAPO's group-relative advantage to a tree structure. It ensures that the gradient signal at each branching node is centered, preventing the policy from simply reinforcing all paths from a "lucky" backtracking node.

## 3. The "Linguistic vs. Logical" Entropy Ambiguity
The paper assumes that maximum entropy tokens correspond to logical decision points (§1).
- **Logical Gap**: Autoregressive entropy $H(w_t)$ does not distinguish between **semantic uncertainty** (e.g., choosing a calculation step) and **syntactic uncertainty** (e.g., choosing between "Next," "Then," or "First,"). 
- **Implication**: If $w^b$ is a syntactic token, the $G$ expansion branches explore phrasing variance rather than reasoning trajectories. The 1.37x speedup claim (§4.2) is also sensitive to this: if max-entropy tokens tend to occur early (e.g., at sentence starts), KV cache reuse is low. The paper lacks an analysis of the token-type distribution of the selected backtracking points.

## 4. Efficiency Gain Sensitivity
The claimed 1.37x speedup over DAPO relies on KV cache reuse from the root to $w^b$.
- **Observation**: If $w^b$ is at position $t$ in a chain of length $L$, the reuse ratio is $t/L$. 
- **Finding**: The speedup is highly sensitive to the temporal distribution of high-entropy nodes. If reasoning models concentrate uncertainty at the end of chains (verification steps), speedup is high. If uncertainty is high at the start (strategic planning), speedup is low. The paper should report the average relative position of $w^b$ to ground this efficiency claim.
