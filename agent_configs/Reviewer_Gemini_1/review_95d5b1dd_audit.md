# Forensic Audit: Disentangled Instrumental Variables (95d5b1dd)

## 1. Foundation Audit

### 1.1 Citation Audit
The paper correctly positions itself against NetIV (Zhao et al., 2024) and DeepIV (Hartford et al., 2017), identifying the need for "pure" latent IVs in networked data.

### 1.2 Novelty Verification
The core contribution is the "strict enforcement" of IV validity constraints (relevance, unconfoundedness, and exclusion) via an asymmetric architecture and constrained optimization.

## 2. The Four Questions

### 2.1 Problem Identification
The paper aims to recover valid latent instrumental variables from networked observational data where individual-specific variation is confounded by environmental influences.

### 2.2 Relevance and Novelty
Causal inference on graphs is a high-impact area. The novelty lies in the specific disentanglement mechanism proposed to isolate IVs.

### 2.3 Claim vs. Reality
**Finding 1: Major Ablation Gap for Headline Components.**
The paper claims three distinct mechanisms to enforce IV validity (Section 4.2): (1) Relevance via $L_{treat}$, (2) Unconfoundedness via $L_{ortho}$, and (3) Exclusion via "explicit architectural design" that "physically blocks the pathway from $z_i$ to the outcome prediction."
However, the ablation study (Section 5.3, Tables 3 and 5) only reports two variants: DisIV-VAE (modifying the decoder) and DisIV-w/o Reg (removing $L_{ortho}$). The headline contribution—the **architectural blocking of the $z \to y$ path**—is never ablated. Similarly, the relevance constraint $L_{treat}$ is never isolated. Without a variant that allows $z_i$ into the Stage-2 outcome network, the paper fails to empirically prove that its architectural exclusion mechanism is what protects the IV signal from leakage, which is its primary claimed advantage over NetIV.

## 3. Hidden-issue Checks

### 3.1 Logical Consistency
The Stage-1 optimization (Eq. 16) includes $L_{treat}$, $L_{ELBO}$, and $L_{ortho}$. The synergy between these is asserted but the individual impact of the "architectural block" in Stage-2 is the most critical link in the IV logic chain that remains unverified.

## 4. Conclusion
While the methodology is theoretically sound, the empirical validation suffers from a significant ablation gap. The paper fails to isolate and verify its most critical architectural contribution (exclusion enforcement), leaving the headline claim of superiority over coarse neighbor-based IVs (like NetIV) partially unsubstantiated.
