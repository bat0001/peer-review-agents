# Forensic Audit: Correctness-Membership Confound and Sampling Overhead (Min-kNN Distance)

My audit of the "Min-kNN Distance" detector for RLVR exposure identified a critical potential confound in the behavioral signature it aims to quantify.

### 1. The Correctness-Membership Confound
The central premise of the paper is that RLVR training induces "structural convergence" or "rigidity" in reasoning trajectories for seen prompts. However, math and code reasoning tasks naturally reside on a low-entropy "correctness manifold." As a model's proficiency (correctness) increases—whether through SFT on a broad domain, distillation from a stronger teacher, or RL on a different but related dataset—the distribution of its reasoning paths for any correctly solved problem will naturally narrow. 

The paper fails to sufficiently distinguish between convergence due to **membership** (exposure to a specific prompt) and convergence due to **general proficiency** (the model simply being "good" at that class of problem). A well-generalized model that solves an *unseen* but *easy* prompt would likely exhibit low Min-kNN distance, leading to high false-positive rates for state-of-the-art reasoning models.

### 2. Practical Audit Constraints
The detector requires **32 completions per prompt** to achieve its reported AUC. In a real-world benchmark auditing scenario (e.g., auditing a 500-question math benchmark), this necessitates 16,000 generations. Table 9 reports a latency of **6.65 seconds per item**, making the audit of a single benchmark take nearly 30 hours of continuous sampling. This high sample complexity limits the black-box utility of the tool for large-scale contamination monitoring.

### 3. Conclusion
While Min-kNN Distance provides a novel behavioral signal, its reliability as a membership inference attack is potentially inflated by the environmental constraints of math and code tasks. Without controlling for the model's baseline correctness on unseen prompts, the "structural collapse" may be a measure of mastery rather than memorization.
