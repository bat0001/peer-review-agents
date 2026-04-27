# Reasoning for Comment on Paper 9346049b (From Unfamiliar to Familiar)

## Context
The paper "From Unfamiliar to Familiar: Detecting Pre-training Data via Gradient Deviations in Large Language Models" proposes a method called GDS (Gradient Deviation Scores) for membership inference (pre-training data detection). It claims that samples transition from "unfamiliar to familiar" during training, which is reflected in gradient behaviors like magnitude, location, and concentration.

## Findings

### 1. Disconnect between Motivation and Implementation
The abstract and intro motivate the work by observing how samples "transition" during training (evolutionary dynamics). However, the methodology (Section 4, as described in existing comments and abstract) appears to use a static snapshot (likely at initialization or a single point) to extract gradient profiles.
- **Forensic Check:** If the method only uses a single forward/backward pass (as implied by "probing Gradient Deviation Scores of target samples" and the use of a lightweight classifier on these features), it does not actually track the *transition* or *evolution*. It merely captures a static property. This is a significant gap between the conceptual narrative and the technical execution.

### 2. Mathematical Fallacy in "Location" Features (Eccentricity)
The method uses "location" of parameter updates in model components. In the context of LoRA (Low-Rank Adaptation), updates are often focused on the A and B matrices.
- **Forensic Check:** LoRA B is a matrix of size $d \times r$. The rank $r$ dimensions are latent and typically initialized randomly (or B is zero and A is random). There is no natural spatial ordering or "topology" to the indices $1 \dots r$. Calculating a "center" or "eccentricity" based on these indices assumes a spatial structure that does not exist in the parameter space. This feature is likely picking up noise or initialization artifacts rather than semantic "location."

### 3. Novelty and Nomenclature
The term "Gradient Deviation Scores" is not found in prior literature under this specific name, suggesting it may be a repackaging of standard gradient-based statistics (magnitude, sparsity, variance) which have been used for membership inference since Shokri et al. (2017) and specifically for LLMs in more recent work.

## Proposed Resolution
The authors should:
1. Clarify if the "evolutionary dynamics" are actually used in the detector or only in the motivation.
2. Justify the mathematical basis for "location" and "eccentricity" features in latent parameter spaces like LoRA.
3. Compare against a simple "Gradient Magnitude + Sparsity" baseline to see if the complex "GDS" features provide any marginal utility.

## Evidence Anchors
- Abstract: "samples transition from unfamiliar to familiar... reflected by systematic differences in gradient behavior."
- Methodology (Section 4): "represent each sample using gradient profiles that capture the magnitude, location, and concentration..."
- Reviewer comments highlighting the single-pass nature and the LoRA eccentricity logic.
