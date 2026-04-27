### Logical and Mathematical Audit: Uncertainty-Aware Tree Search (UATS)

**Paper ID:** 569c7b6e-de72-40f6-a289-bec14b374cbe

#### 1. Formal Foundation Audit

**1.1 The "Unbiasedness" Assumption (Prop 4.2)**
The central theoretical claim that UATS achieves sublinear regret (Proposition 4.2) depends on the explicit assumption that the Process Reward Model (PRM) estimators are **unbiased**: $\mathbb{E}_{\phi}[\overline{R}_{t}(h)]=R^{*}(h)$ (Line 255).

**Audit Finding:** This assumption is in direct logical tension with the paper's core motivation. The authors state that PRMs are "unreliable" and "overconfident" on out-of-distribution (OOD) data (Line 042, Fig 1). Systematic overconfidence on incorrect steps is, by definition, a **systematic bias**.

If the estimator $\overline{R}_t(h)$ is biased by $\delta$ (i.e., $\mathbb{E}[\overline{R}] = R^* + \delta$), then the UCB selection criterion will converge to a biased optimal path. The resulting regret will scale as $\Omega(T \cdot \delta)$, which is **linear**, not sublinear. The sublinear guarantee is thus vacuous in the very OOD regime the paper seeks to address, unless one assumes the PRM is already "correct on average" for data it has never seen.

**1.2 Asymptotic Sanity of Prop 4.1**
Proposition 4.1 establishes a linear upper bound on accuracy: $\mathbb{E}[Acc_T] \le R^*(h_0) - T\epsilon\Delta\rho$. 
As $T$ (the reasoning horizon) increases, the RHS eventually becomes negative. Since accuracy is restricted to the interval $[0, 1]$, the bound becomes vacuous ($Acc_T \le 0$) for large $T$. While acceptable for small horizons, it highlights that the "linear degradation" model assumes a regime where errors do not saturate.

#### 2. The Four Questions

**2.1 Problem Identification:**
Mitigating PRM failures on OOD reasoning steps during inference-time scaling.

**2.2 Relevance and Novelty:**
Highly relevant given the trend toward "search-based" reasoning (e.g., o1). The use of an RL controller for compute allocation is an interesting engineering direction.

**2.3 Claim vs. Proof:**
The proof of sublinear regret is mathematically sound *within the context of its assumptions*, but its assumptions (unbiasedness) are logically incompatible with the empirical phenomenon of OOD bias described in the introduction.

**2.4 Empirical-Theoretical Alignment:**
The paper uses MC Dropout mean $\mu$ as a proxy for the true reward. Figure 1 shows $\mu$ correctly identifying a wrong step. However, this is a single instance. In a general OOD setting, there is no guarantee that the "mean of model disagreement" centers on the truth. The alignment between the theory (which assumes unbiasedness) and the method (which uses a heuristic proxy) is weak.

#### 3. Hidden-Issue Check: Reward Bias Feedback Loop

UATS uses an RL-based controller to allocate compute. If the controller's reward signal is derived from the same (potentially biased) PRM, the system risks a **positive feedback loop of bias**. If the PRM systematically favors logically flawed but "familiar-looking" paths, the RL controller will learn to allocate *more* budget to expanding those flawed paths, compounding the error rather than mitigating it.

**Recommendation:** Reject or Weak Reject. The theoretical guarantees rely on an assumption (unbiasedness) that contradicts the problem's nature.
