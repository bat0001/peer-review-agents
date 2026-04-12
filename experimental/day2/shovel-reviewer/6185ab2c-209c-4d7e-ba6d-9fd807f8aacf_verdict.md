# Reproducibility Audit: Robustness in Text-Attributed Graph Learning: Insights, Trade-offs, and New Defenses

### Summary
This paper unearths a "text-structure robustness trade-off" in Text-Attributed Graph (TAG) learning through a massive benchmarking effort across GNNs, RGNNs, and GraphLLMs. It proposes SFT-auto, a multi-task fine-tuning framework that aims to provide balanced robustness. The scale of the digging—10 datasets and multiple attack models—is a sturdy bit of systems hygiene.

### Findings
The paper's strongest reproducibility signal is the release of code and the use of standard datasets (Cora, CiteSeer, PubMed, etc.). The empirical finding that RGNNs like GNNGuard benefit significantly from better text encoders is well-documented and checkable. However, the SFT-auto defense has some shallow spots: the exact LLM backbones used for all comparisons are not always explicitly stated in the summary text, and the multi-task detection-prediction pipeline requires specific hyperparameters (learning rate, detection threshold) that are not fully unearthed in the main text.

### Open Questions
- What is the variance of the SFT-auto performance across multiple independent fine-tuning runs?
- How sensitive is the "detection-prediction" pipeline to the choice of the underlying LLM's scale and reasoning capability?

### Method Description Completeness
The benchmarking framework is well-described at a high level. The SFT-auto method is conceptualized as multi-task SFT, but the precise prompt structures and fine-tuning configurations need more detail for a from-scratch reimplementation without the code.

### Experimental Setup Completeness
Audit of datasets, splits, and attack types is comprehensive. The paper correctly matches clean performance before assessing robustness, which is a vital bit of experimental rigor.

### Code and Artifact Availability
Code is available at the provided GitHub URL, which provides the necessary leverage for full Level 4 reproducibility.

### Computational Requirements
Training GraphLLMs and performing multi-task SFT is computationally heavy compared to traditional GNNs. The paper notes the complexity is comparable to other SFT methods, but independent verification will require significant GPU resources.

### Transparency Assessment
The authors are transparent about the GraphLLM vulnerabilities (poisoning). The documentation of the trade-off across ten datasets suggests a deep and honest audit of current model limitations.

### The Email Test Result
Minor-to-significant gaps. Handing just the paper to a researcher would likely result in questions about the LLM fine-tuning specifics. The code is essential for filling these gaps.

### Overall Reproducibility Verdict
**Mostly reproducible.** The presence of code and standard datasets makes this a firm foundation for others to build upon.

---
**Score Justification**: The paper is an exceptionally thorough benchmarking study with a practical (if compute-heavy) defense. The reproducibility is high due to the code release and systematic evaluation.
**Final Verdict**: Accept
