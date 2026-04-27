# Empirical Audit Reasoning - Paper 2640f7ad (CycFlow)

## Finding: Ambiguous Time Reporting in Table 1

### Description
Table 1 compares the "Time" for various TSP solvers. However, the reported values appear to mix total test set times with per-instance times, leading to confusing comparisons. Specifically, the relationship between "AM" (6s) and "CycFlow" (0.01s) for TSP-100 is inconsistent with known performance characteristics of these models.

### Evidence
- **AM Baseline:** The paper cites Kool et al. (2018) for the Attention Model (AM). In that paper, AM on TSP-100 is reported to take approximately 6 seconds for 1,000 instances (i.e., 0.006s per instance).
- **CycFlow ours:** CycFlow is reported to take 0.01s. If this is per-instance, then CycFlow is actually **slower** than AM (0.01s vs 0.006s). If 0.01s is the total time for the test set, it would imply a per-instance time of 1 microsecond (assuming 10,000 instances), which is physically impossible for a Transformer-based model with spectral sorting.
- **Concorde Baseline:** Concorde is reported as 12m for TSP-100. For a standard test set of 10,000 instances, this would be ~0.072s per instance, which is correct. This suggests that "Time" in Table 1 refers to **total time for the test set**.
- **Inconsistency:** If 12m and 6s are total times, then CycFlow's 0.01s total time implies a per-instance speed that is orders of magnitude faster than the time required to even load the coordinates into GPU memory.

### Impact
The lack of clarity regarding whether "Time" is per-instance or total, and the apparent inconsistency in these measurements, makes it difficult to verify the claimed "three orders of magnitude" speedup. It also obscures whether CycFlow is actually faster than established constructive baselines like AM.

### Proposed Resolution
The authors should explicitly state the size of the test set and clarify whether the reported times are per-instance or total. If total, the 0.01s measurement should be double-checked for correctness, as it implies a sub-microsecond per-instance budget.
