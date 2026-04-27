# Formal Audit: The Chicken and Egg Dilemma: Co-optimizing Data and Model Configurations for LLMs

## 1. Problem Identification
The paper addresses the joint optimization of training data mixtures and model configurations (LoRA hyperparameters) for LLMs. It proposes JoBS, an algorithm that uses a neural network performance predictor to estimate full-training performance from short runs, thereby increasing the number of Bayesian Optimization (BO) iterations possible within a fixed budget.

## 2. Claim vs. Proof Audit: Soundness of the Predictor Error Assumption

**Assertion:** The theoretical convergence of JoBS (Theorem 5.1) rests on a strong and unvalidated assumption regarding the scaling of the predictor's error.

**Evidence:**
1.  **Assumption (Page 6):** The authors assume that the prediction error $\epsilon$ of the neural network $F$ is $R$-sub-Gaussian with $R = k/\sqrt{N}$, where $N$ is the number of full-training runs used to train the predictor. 
2.  **Theoretical Impact:** This $1/\sqrt{N}$ scaling is critical for the regret bound in Equation 3 ($R_T = O(\dots + \frac{k}{\sqrt{N}} \dots)$). It provides the mathematical basis for deriving an "optimal $N$" that balances initial profiling cost against BO iteration fidelity.
3.  **Logical Gap:** While a $1/\sqrt{N}$ rate is common in parametric estimation, its application to a neural network predictor over the complex, non-linear, and potentially non-smooth landscape of LLM performance is speculative. The performance landscape $L(X, M)$ depends on complex interactions between data mixtures and LoRA configurations. If the landscape has high-frequency components or "cliff-like" transitions, $N=30$ random Sobol samples may not be sufficient to enter the $1/\sqrt{N}$ error regime.

**Result:** Without empirical or theoretical validation of the $1/\sqrt{N}$ error scaling for the specific neural predictor used, the optimality of the budget allocation (Section 5.4) and the convergence guarantees of Theorem 5.1 are theoretically "soft". If the error does not scale as assumed, JoBS could allocate too little budget to profiling, leading to a biased predictor that misguides the BO search into suboptimal regions.

## 3. Dimensional/Asymptotic Consistency
The regret bound $R_T$ in Equation 3 is dimensionally consistent with standard IGP-UCB bounds (Chowdhury & Gopalan, 2017), with an additional term to account for the predictor's noise. The tradeoff between $N$ and $T = (C-NB)/B_{small}$ is correctly captured in the asymptotic notation.

## 4. Resolution Proposal
The authors should provide an empirical validation of the $R = k/\sqrt{N}$ assumption by plotting the prediction error variance across a wider range of $N$. Furthermore, a "safety" mechanism in Algorithm 1, such as periodically performing high-fidelity evaluations to "ground" the predictor, would mitigate the risk of the search converging to a spurious maximum.
