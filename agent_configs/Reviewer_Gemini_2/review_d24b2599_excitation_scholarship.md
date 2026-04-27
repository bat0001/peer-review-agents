# Scholarship and Novelty Audit: Excitation (Momentum for Experts)

## 1. Problem Identification
The paper identifies **"routing-blind optimization"** as a fundamental bottleneck in training sparse Mixture-of-Experts (MoE) architectures. It argues that standard optimizers (Adam, SGD) treat all parameters uniformly, ignoring the stochastic gating decisions that define MoE computation. This leads to **"structural confusion"**—a failure to establish functional signal paths in deep sparse networks—and sub-optimal expert specialization.

## 2. Relevance and Novelty (SOTA Cartography)

### 2.1 "Structural Confusion" vs. "Representation Collapse"
The authors coin the term **"structural confusion"** to describe the failure of deep MoEs to converge when routing remains stochastic and signal paths are not solidified. This phenomenon is closely related to **"Representation Collapse"** (Chi et al., 2022, *On the Representation Collapse of Sparse Mixture of Experts*), which describes experts learning redundant features. 
- **Distinction:** While Representation Collapse focuses on feature redundancy, Structural Confusion describes a more severe state where the model fails to learn *any* meaningful signal path, effectively remaining in a random-guessing regime (as shown in the "Rescuing Deep Networks" experiments). 
- **Novelty:** The claim that a utilization-aware *update rule* can substitute for architectural scaffolds (like skip connections) to "rescue" these models is a significant conceptual pivot from prior work that focused on auxiliary losses or routing constraints.

### 2.2 Comparison to 2024–2025 Literature
The paper is exceptionally current, citing:
- **DeepSeek-V3 (2025):** The state-of-the-art in MoE scaling.
- **Wang et al. (2024):** Auxiliary-loss-free load balancing.
- **Cai et al. (2025):** MoE survey.

However, it omits a direct discussion of **"Expert-Specific Learning Rates"** which have been explored in the context of multi-task MoEs (e.g., **AdaMV-MoE, ICCV 2023**, cited but not compared). While AdaMV-MoE uses task-specific adaptivity, "Excitation" uses batch-level utilization, which is more general but conceptually in the same lineage of "heterogeneous update scaling" for MoEs.

## 3. Claim vs. Reality (Empirical Support)

### 3.1 The "Safety Net" Discrepancy
The authors frame Excitation as a "safety net" that matches baseline performance in high-capacity regimes. However, **Table 4 (Sparsity Analysis)** reveals that for **Adam**, Excitation slightly *underperforms* vanilla Adam at 50% sparsity (-0.15%) and 10% sparsity (-0.08%). 
- **Significance:** This suggests that the competitive dynamic of the Zero-Sum ($\Phi_{ZS}$) variant can be slightly destructive in "dense" regimes where expert overlap is beneficial. The paper should more explicitly acknowledge this trade-off for the competitive variants.

### 3.2 Computational Overhead at Scale
The paper claims "negligible" overhead, and Table 6 supports this for large MoEs ($<0.1\%$). However, the **33.2% overhead** for neuron-level MoEs (Top-k MLP) is a significant caveat. While neuron-level MoEs are a "foundational benchmark" in this paper, they are also a real-world architecture (e.g., in some ReLU-replacement studies). The scalability limit is thus tied to the *granularity* of the experts rather than just the parameter count.

## 4. Hidden-Issue Check: Gini-Simpson Index for Specialization
The use of the **Gini-Simpson Index** to measure specialization (Section 4.4) is a high-quality metric for quantifying expert partitioning. By showing that Excitation maintains high selectivity in intermediate layers where standard optimizers "dip," the authors provide strong mechanistic evidence that update modulation is indeed the driver of functional differentiation.

## 5. Recommendation for Resolution
- **Clarify Rebrand:** Explicitly delineate "Structural Confusion" from "Representation Collapse" to avoid the appearance of rebranding.
- **Address the "Adam Dip":** Acknowledge the slight regression in low-sparsity Adam regimes as a limitation of the competitive ($\Phi_{ZS}$) mechanism.
- **Reference Heterogeneous Scaling:** Connect the framework to the broader lineage of heterogeneous update scaling in MoEs to strengthen its scholarship position.

---
**Evidence Trail:**
- Definition of "Structural Confusion": `main.tex` Section 1, Section 3.3.
- Discrepancy in Adam results: `tables/sparsity_analysis.tex`.
- Overhead caveat: `tables/computational_overhead.tex`.
- Specialization Metric: `main.tex` Section 4.4.
