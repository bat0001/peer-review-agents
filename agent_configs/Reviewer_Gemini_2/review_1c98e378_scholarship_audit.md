# Reasoning and Evidence for Review of SQUAD (1c98e378)

## Literature Mapping

### Problem Area
Early-Exit Neural Networks (EENNs) efficiency and reliability, specifically focusing on the unreliability of single-model confidence thresholds for stopping.

### Prior Work Mapping
- **Early-Exit Neural Networks:** Direct prior work (Teerapittayanon et al., 2017; Scardapane et al., 2020).
- **Neural Ensemble Search:** Direct prior work (Shu et al., 2022 - NESBS).
- **Ensemble of Early Exits:** Related work (Qendro et al., 2021; Ghanathe et al., 2025).
- **Hierarchical Diversity:** Novel conceptual contribution introduced in this paper to address multi-stage ensemble consensus.

## Citation Audit
- `branchynet`: Real paper (2017). Metadata matches.
- `nachos`: Real paper (2025). Metadata matches.
- `nesbs`: Real paper (2022). Metadata matches.
- `QUTE`: Real paper (2025). Metadata matches.
- The bibliography accurately represents the state of the field in early 2026.

## Analysis of Claims

### 1. Robustness of the t-test for Small Ensembles ($K$)
**Potential Vulnerability:** The SQUAD framework utilizes a one-sided t-test (Equation 7) to decide whether to trigger an early exit. For the experiments conducted, the number of ensemble members $E$ (likely referring to $K$ in the text) is set to 3.
**Evidence:** For $K=3$, the consensus subset $S_e$ has a size of 2 or 3. At $|S_e|=2$, the degrees of freedom $df=1$, and the critical t-value for 95% confidence is $t_{0.05, 1} = 6.314$. 
**Problem:** The Lower Confidence Bound (LCB) formula $LCB = \mu - t \cdot \sigma/\sqrt{|S_e|}$ becomes extremely sensitive to the sample standard deviation $\sigma$. With $df=1$, even a small disagreement between the two voting members will drastically deflate the LCB, potentially making the exit condition unreachable for $\tau_{conf} > 0.5$. This suggests that for small ensemble sizes, the t-test may effectively default to a "unanimous and high-confidence" requirement, which might be overly conservative and could negate the efficiency gains of the "quorum" mechanism.

### 2. Inference Parallelism and Latency ($F_M$)
The paper proposes a MACs-aware protocol that "queries each learner incrementally in order of computational complexity." 
**Clarification Needed:** In a Truly Parallel Edge system (e.g., multi-core DSP), all $K$ learners would ideally start simultaneously. The "first-come first-vote" logic implies that the latency is determined by the $m$-th fastest learner reaching consensus. However, the $F_M$ metric (sum of maximum MACs among voting members) and the $F_{MT}$ energy metric (including parallel overhead) assume that background branches are interrupted. Practical implementation on hardware with fixed-size thread pools might face scheduling overheads that aren't captured by MAC counts, especially when frequent synchronization for the t-test is required at every exit stage.

### 3. Hierarchical Diversity and QUEST
The introduction of **Hierarchical Diversity** as an explicit NAS objective is a strong conceptual move. By adapting NESBS to optimize diversity at every intermediate gate (Section 5.4), QUEST ensures that the ensemble is robust to errors at multiple depths, not just at the final output. This is well-supported by the PPD results in Table 5.

## Proposed Resolution
- Acknowledge the sensitivity of the t-test at low $K$ and clarify if the framework is intended for larger ensembles (e.g., $K \ge 5$) to leverage the statistical benefits.
- Provide a more detailed discussion on the hardware-level synchronization requirements for the stage-wise quorum mechanism.
- Clarify the relationship between $F_M$ and wall-clock latency on parallel vs. sequential hardware.
