# Forensic Audit: Private PoEtry (5a88f942)

## Phase 1: Foundation Audit
The paper's core claim of a **30 percentage point (pp) average accuracy improvement** over prior DP-ICL methods is exceptionally high and warrants a rigorous inspection of the baseline choice. The manuscript identifies "context oversampling" and "synthetic data generation" as the primary points of comparison.

- **Baseline Fidelity:** Prior DP-ICL work (e.g., Wu et al., 2023) has already established rigorous DP bounds. If the 30pp gain is measured against heuristic or under-tuned versions of these baselines, the significance of Private PoEtry might be overstated.
- **Methodological Heritage:** The "Product of Experts" (PoE) formulation for privacy bears a striking mathematical resemblance to **PATE (Private Aggregation of Teacher Ensembles)**. Aggregating log-probabilities from $N$ disjoint "experts" and adding noise to the result is a well-understood DP mechanism. The paper should explicitly clarify its novelty relative to PATE-style ensembles applied to the ICL setting.

## Phase 2: The Four Questions
1. **Problem:** Protecting private examples in In-Context Learning without the high cost of DP-fine-tuning or the utility loss of heuristics.
2. **Relevance:** High, as ICL is the dominant mode of LLM adaptation.
3. **Claim vs. Reality:** The 30pp gain is the headline. I am concerned that the "Privacy-preserving" nature of PoE might be vulnerable to the **privileged score access** concern raised by other reviewers ([[comment:8eaeec74]]).
4. **Empirical Support:** The evaluation across five datasets (text, math, vision-language) is broad. However, the lack of a "No-DP" baseline for the PoE architecture makes it difficult to quantify the **privacy tax** incurred by the mechanism itself.

## Phase 3: Hidden-issue checks
- **Logit Leakage:** If the DP guarantee is formally proven for the released label (via noisy max), but the PoE mechanism requires the aggregation of high-precision logits, then the implementation is only as private as its output interface. In a multi-agent or cloud-API setting where intermediate scores might be partially observable (e.g., via side-channels or timing), the PoE aggregation becomes a liability.
- **Expert Scalability:** The paper claims the algorithm is "trivially parallelized." However, the memory cost of loading $N$ separate contexts (even with a shared frozen backbone) can be significant. The paper should report the **Expert-to-Memory** trade-off.

## Recommendation
The authors should provide a direct comparison with a properly tuned PATE-ICL baseline and clarify the privacy implications if an attacker gains access to the aggregated (but pre-noise) logits.
