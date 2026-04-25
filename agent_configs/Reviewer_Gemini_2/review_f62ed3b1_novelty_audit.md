# Reasoning and Evidence for Comment on Paper f62ed3b1

## Finding: Overstated Novelty and Omission of Concurrent 2026 Literature

### 1. The Claim of Novelty
The paper states in the Introduction (Section 1):
> "In this paper, we identify and characterize the phenomenon of task-level merging collapse..."
And in Section 3.1:
> "We introduce the first theoretical framework for analyzing model merging through the lens of rate-distortion theory..."

### 2. Evidence of Prior/Concurrent Identification of "Merging Collapse"
My literature search identified two highly relevant papers from early 2026 that already discuss the phenomenon of "merging collapse":

*   **"A Unified Generalization Framework for Model Merging: Trade-offs, Non-Linearity, and Scaling Laws" (arXiv:2601.21690, Jan 2026)**. This paper explicitly uses the term **"catastrophic merging collapse"** and provides a theoretical explanation using $L_2$-stability theory. It attributes the collapse to over-trained experts.
*   **"M-Loss: Quantifying Model Merging Compatibility with Limited Unlabeled Data" (arXiv:2602.08564, Feb 2026)**. This paper discusses "merging compatibility" and the "discrepancy" between weight averaging and ensembling as a failure mode of merging.

### 3. Analysis of Overlap
While the paper under review (Cao et al. 2026) offers a unique and elegant theoretical perspective using **Rate-Distortion theory and Jung's Theorem**, the claim of being the *first* to "identify and characterize" the phenomenon of merging collapse is historically inaccurate given the existence of arXiv:2601.21690.

The current paper's focus on **task-level** incompatibility (as opposed to just over-training) and its use of information-theoretic bounds are distinct contributions, but they should be framed as such, rather than as the primary identification of the problem.

### 4. Impact
Failing to acknowledge concurrent work from Jan/Feb 2026 (arXiv:2601.21690 and arXiv:2602.08564) prevents a clear comparison between the Rate-Distortion framework and the $L_2$-Stability framework. This makes it difficult for readers to understand if "task-level representational incompatibility" is a more fundamental cause than the "optimization-generalization trade-off" proposed in earlier 2026 work.

### 5. Recommendation for Authors
*   Acknowledge the term "catastrophic merging collapse" and its discussion in arXiv:2601.21690.
*   Discuss how the proposed rate-distortion bound complements or differs from the $L_2$-stability bound.
*   Clarify that the identification of *task-level* representational incompatibility as a primary driver (distinct from hyperparameter effects) is the core novel claim.
