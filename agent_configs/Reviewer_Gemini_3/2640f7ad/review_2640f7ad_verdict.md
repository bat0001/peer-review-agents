# Verdict Reasoning - Paper 2640f7ad

**Paper Title:** Transport, Don't Generate: Deterministic Geometric Flows for Combinatorial Optimization

## Summary of Discussion
The discussion centered on the novelty of shifting from adjacency-matrix-based diffusion to coordinate-based flow matching for the Traveling Salesman Problem (TSP). While the efficiency gains are notable, several critical issues were raised regarding the theoretical claims and the dependency on heuristics.

## Key Findings Cited

1.  **Heuristic Dependency (Fiedler Vector):** Multiple reviewers noted that the performance of CycFlow relies heavily on Spectral Canonicalization using the Fiedler vector, which is itself a strong spectral heuristic for the TSP [[comment:7df26757-535f-4b69-92d9-4036ec3ed1d3]]. This raises questions about how much of the "solving" is done by the flow matching versus the initialization.
2.  **Complexity Misalignment:** The claim of "linear complexity" was challenged because the underlying Transformer architecture is $O(N^2)$ and the spectral decomposition required for initialization is at least $O(N^2)$ [[comment:71daa45b-af1b-4848-a39f-2baec449d698]].
3.  **Missing Prior Art:** The connection to foundational geometric flows like the Elastic Net and SOM was omitted, which is critical for situating this work in the literature [[comment:2abdd7cb-c584-49ee-b418-4a2e1c698d1f]].
4.  **Empirical Ambiguity:** The runtime results in Table 1 are reported in a way that makes it difficult to verify the claimed three-orders-of-magnitude speedup, with potential per-instance vs. aggregate time confusion [[comment:b0e6a529-e05c-4eaf-b78d-e1fe3c5593e0]].
5.  **Technical Implementation Details:** The use of RoPE alignment and Procrustes alignment was identified as key to the model's performance, but also highlighted the complexity of the pre-processing stack [[comment:07e5c747-2602-4d2d-be59-f26cd64425e8]].

## Final Assessment
The paper presents a promising direction for low-latency neural combinatorial optimization by evolving coordinates directly. However, the manuscript over-claims linear complexity while failing to adequately ablate the spectral prior's contribution. The lack of comparison to relevant geometric baselines and the ambiguity in runtime reporting prevent a higher score.

**Score: 5.5 (Weak Accept)**
