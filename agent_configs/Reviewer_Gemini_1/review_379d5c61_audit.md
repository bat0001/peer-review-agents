# Forensic Audit: GRXForm (379d5c61)

## 1. Foundation Audit

### 1.1 Citation Audit
The paper relies on the "Dr. GRPO" formulation, citing Liu et al. (2025), "Understanding r1-zero-like training: A critical perspective."

### 1.2 Novelty Verification
The core contribution is applying a variance-reduced GRPO variant to molecular scaffold elaboration.

## 2. The Four Questions

### 2.1 Problem Identification
The paper addresses the high variance and generalization failure in amortized molecular optimization across heterogeneous chemical scaffolds.

### 2.2 Relevance and Novelty
Relevant for drug discovery. The novelty lies in the instance-specific normalization using GRPO.

### 2.3 Claim vs. Reality
**Finding 1: Highly Suspect Baseline Results (Table 2).**
In Table 2 (L281), the authors report that all five baselines (GraphXForm, LibINVENT, DrugEx v3, Mol GA, and GenMol) achieve a **0.000 Success Rate**, while GRXForm achieves 0.178 (17.8%). An "all-zero" baseline result across diverse paradigms (amortized and instance-based) is a massive red flag. It suggests that the success criteria (L250) or the constrained-generation wrappers applied to the baselines were either incompatible or unfairly restrictive. For instance, the authors admit that for Mol GA, they enforced preservation as a "hard constraint" which "leads to a high rejection rate... effectively stalling the evolutionary search" (L301). A fair comparison should optimize the baselines within their own native capabilities.

## 3. Hidden-issue Checks

### 3.1 Logical Consistency
**Finding 2: Potential Misattribution of "Dr. GRPO" Modifications.**
Section 3.2 (L226) claims to adopt the "Dr. GRPO formulation" from Liu et al. (2025) and attributes two specific modifications to it: (1) dropping the division by group standard deviation and (2) removing the normalization by trajectory length. However, the cited paper title "Understanding r1-zero-like training" suggests a theoretical analysis of existing R1-style training rather than a proposal for these specific "Dr. GRPO" modifications. It is unclear if these modifications originate from the cited work or are the authors' own inventions misattributed to a "Dr. GRPO" name.

## 4. Conclusion
GRXForm demonstrates improved stability for scaffold decoration, but the empirical case is weakened by a benchmark where all baselines are reported as complete failures (0% success). This suggests a lack of baseline parity in the experimental setup. Furthermore, the attribution of the "Dr. GRPO" modifications requires clarification to ensure citation integrity.
