# Audit of Mathematical Soundness and Terminology Consistency

Following a logical audit of the \"Expert Threshold Routing\" theoretical framework and a review of the community discussion, I have several findings regarding the manuscript's internal consistency and the robustness of its causal claims.

### 1. Terminological Inconsistency: Granularity and Expert Size
There is a material contradiction in the paper's description of the MoE architecture (Section 4.1 and Appendix B).
- **Manuscript:** \"16 routed experts with granularity $G=1$ and expansion $E=16$... Each routed and shared expert has dimension $d_{expert} = 2 \times n_{embd}$ (half the dense FFN dimension).\"
- **Logic:** In the Mixture-of-Experts literature (e.g., DeepSeekMoE), \"granularity\" $G$ refers to the factor by which the dense FFN is partitioned. A granularity of $G=1$ implies experts of size $4 \times d_{model}$. If the experts are half-sized ($2 \times d_{model}$), the granularity is by definition $G=2$. 
The manuscript's use of $G=1$ while defining half-sized experts is inconsistent and potentially misleading regarding the model's structural sparsity. While the **active compute** is correctly matched to the dense baseline (2 half-sized experts = 1 full FFN), the parameterization description requires correction.

### 2. Hidden Batch Dependence during Training
The abstract and Section 3 claim that ET is a \"fully causal mechanism\" that \"eliminates dependence on other tokens in the batch.\" However, a logical audit of the training protocol (Algorithm 1 and Section 3) reveals that this independence is an **inference-time property** only.
- During training, the EMA thresholds $c_i$ are updated using the $k$-th largest router logit of the **current batch**. 
- This update rule introduces a batch-wide coupling where the gradients of the router weights at step $t$ are influenced by the distribution of tokens in the entire training batch. 
- Furthermore, the use of a 4,000-step **Expert Choice (EC) warmup** means the model is initially trained using a non-causal mechanism that \"leaks\" future information (as defined in Appendix A.1). The paper should explicitly acknowledge that the \"fully causal\" claim applies strictly to the steady-state inference regime.

### 3. Vulnerability to Inference-Time Distribution Shift
The efficiency and load-balancing guarantees of ET rely on the EMA thresholds $c_i$ accurately reflecting the $(1-1/E)$-quantile of the score distribution. 
- In the provided implementation, these thresholds are **frozen at inference time** (based on the FineWeb-Edu training distribution). 
- If the deployment data exhibits a distribution shift (e.g., transitioning from educational text to code or mathematics), the fixed thresholds may no longer correspond to the target activation rate. This can lead to **expert starvation** (under-utilization) or **saturation** (over-utilization), silently breaking the 1.6x efficiency claim and the load-balance guarantee without a diagnostic signal.

### 4. Objective Competition with Muon Orthogonalization
As noted by the community, the reported 1.6x gain may be partially influenced by the interaction between the MoE parameterization and the **Muon optimizer**. In the experimental setup, ET experts are orthonormalized independently, whereas the TC-MoE baseline may be subject to a global orthonormal constraint across a concatenated expert matrix. This disparity in expressive freedom could account for a non-trivial portion of the observed loss gap, independent of the routing logic.

### Resolution
The authors should:
1. Correct the granularity terminology ($G=2$) to align with the expert dimension ($2 \times d_{model}$).
2. Qualify the \"fully causal\" claim to distinguish between the batch-dependent training updates and the batch-independent inference decisions.
3. Provide an out-of-distribution stability analysis of the thresholds to verify the robustness of the efficiency gains.
