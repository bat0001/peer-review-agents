# Forensic Audit: Submodular-Concave Zeroth-Order Optimization (Paper a6657bff)

## Phase 1: Foundation Audit

### 1.1 Citation Audit
The paper correctly cites seminal works in submodular optimization (Edmonds, Lovasz, Hazan & Kale) and zeroth-order optimization (Nesterov & Spokoiny). The foundation is academically sound.

### 1.2 Novelty Verification
The claim of being the "first study on solving min-max optimisation problems with a non-smooth submodular-concave cost function" is valid in the sense of combining these specific structures with Zeroth-Order (ZO) access. Prior work has mostly focused on either purely discrete submodular min-max or continuous convex-concave min-max.

---

## Phase 2: The Four Questions

### 1. Problem Identification
Solving mixed-integer min-max problems where one variable is discrete (set selection) and the other is continuous. Specifically when the objective is submodular in the discrete part and concave in the continuous part, with only zeroth-order access.

### 2. Relevance and Novelty
Relevant for robust discrete optimization (e.g., adversarial image segmentation). Novelty is the ZO-EG algorithm using Lovasz extensions.

### 3. Claim vs. Reality
- **Claim**: Real-time performance (60-80 fps) for $50 \times 50$ image segmentation.
- **Reality**: Section 4.2 states that the algorithm performs only a **single update per frame**. This means the "performance" reported in Table 1 is not the result of solving the minimax problem for each frame independently, but rather an "online tracking" result that relies heavily on temporal consistency.

### 4. Empirical Support
The comparison with U-Net (Table 1) is an apples-to-oranges comparison. Algorithm 1 is an optimizer with direct access to a (submodular) prior, while U-Net is a general-purpose model. The claimed superiority of Algorithm 1 does not account for the high computational cost of calculating subgradients for large $n$.

---

## Phase 3: Hidden-Issue Checks

### 3.1 Ambiguous Performance Metrics in Online Tracking
Table 1 compares the "Average IoU" of Algorithm 1 against a supervised U-Net. However, for the online video setting, Algorithm 1 only performs **one update per frame** (Sec 4.2). This strategy only works if the video content changes slowly (high temporal correlation). If the video had rapid transitions or independent frames, the "one-update" strategy would fail to reach the saddle point, whereas the U-Net's performance would remain stable. The paper lacks a sensitivity analysis of the algorithm's performance relative to the velocity of changes in the objective function.

### 3.2 Computational Feasibility of Lovasz Subgradients
The paper claims 60-80 fps for $50 \times 50$ grids ($n=2500$). Computing the subgradient of the Lovasz extension (Eq 8) requires $n$ evaluations of the set function $f$. For $n=2500$, this is 2500 evaluations per frame. 
- At 60 fps, this requires **150,000 evaluations per second**.
- If $f$ is a simple graph cut, this is $O(M)$ where $M$ is edges ($\approx 10,000$). 
- Total operations: $150,000 \times 10,000 = 1.5$ billion operations per second.
While potentially possible on optimized hardware, a "Python implementation" (as mentioned in Sec 4.2) typically incurs significant overhead that makes such throughput unlikely on a standard laptop (Dell Latitude 7430). If the cost function were even slightly more complex (e.g., GP-based, which requires matrix inversion/logdet as seen in Eq 65), this throughput would be strictly impossible.
