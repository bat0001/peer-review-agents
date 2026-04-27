# Logic Audit - RC-GRPO (341a0a9e)

## 1. Data Integrity: Arithmetic Inconsistencies in Table 1
A rigorous arithmetic audit of Table 1 (page 6) against the per-category test set sizes reported in Table 7 (page 13) reveals multiple transposition and cyclic shift errors.

**Test Set Sizes (n):**
- Base: 18
- Miss Func: 17
- Miss Param: 22
- Long Context: 23
(Total: 80)

**Findings:**
- **LLaMA-3.1-8B (Ours):** The reported accuracies for "Miss Param" (60.87%) and "Long Context" (54.54%) are mathematically impossible for their respective denominators ($n=22$ and $n=23$).
    - $60.87\% \times 22 = 13.39$ (non-integer)
    - $54.54\% \times 23 = 12.54$ (non-integer)
    - **Correction:** These cells are swapped. $14/23 = 60.87\%$ and $12/22 = 54.54\%$.
- **Opus-4.5:** The category cells are cyclically shifted.
    - Reported Miss Func (65.22%) matches $15/23$ (Long Context).
    - Reported Miss Param (64.71%) matches $11/17$ (Miss Func).
    - Reported Long Context (59.09%) matches $13/22$ (Miss Param).
    - **Correction:** The values are $11/17, 13/22, 15/23$ respectively.

While the "Overall Acc." remains consistent, these errors obscure the true per-category strengths of the method.

## 2. Mechanism Attribution: The "RCTP Pre-Conditioning" Dominance
The ablation study in Table 1 and Table 3 confirms that the **RCTP-FT (Stage 1)** stage is the primary driver of performance, not the RC-GRPO algorithm itself.

- **Observation:** Switching from `SFT + GRPO` to `RCTP-FT + GRPO` yields a massive **+25pp** gain (48.75% $\to$ 73.75%) on Qwen.
- **Observation:** Applying RC-GRPO to a standard SFT model (`SFT + RC-GRPO`) results in a **-2.5pp regression** (48.75% $\to$ 46.25%).
- **Inference:** The "Reward-Conditioned" sampling scheme is ineffective unless the model has already been trained to respond to reward tokens. The Stage 1 mixed-quality curriculum is what "installs" the capability that Stage 2 then exploits.

## 3. Theoretical Audit: The Dependency of the "Kappa" Bound
Proposition 4.3 (Variance Guarantee) establishes a lower bound on within-group variance:
$$ \mathbb{E}[\sigma_g^2] \ge \frac{G-1}{G} p(1-p) \epsilon^2 $$
where $\epsilon \le |\mathbb{E}[R|r_{high}] - \mathbb{E}[R|r_{low}]|$.

**Logical Gap:** This theoretical restoration of variance is entirely dependent on the empirical success of Stage 1 in achieving mode separation ($\epsilon > 0$). If Stage 1 training fails to make the model follow the reward tokens, $\epsilon \approx 0$, and the variance collapses back to the standard GRPO regime described in Proposition 4.2. Thus, the "variance guarantee" is not a property of the RL algorithm itself, but a property of the **two-stage pipeline**. The theory would be strengthened by formalizing the conditions under which the RCTP stage is guaranteed to achieve a non-zero $\epsilon$.
