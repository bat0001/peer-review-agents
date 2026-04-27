# Scholarship Audit Reasoning - Paper 2640f7ad (CycFlow)

## Finding: Omission of Foundational Geometric Flow Prior Art

### Description
The paper proposes "CycFlow", which treats the Traveling Salesman Problem (TSP) as a deterministic geometric flow, transporting points from their input coordinates to a canonical circular arrangement. The authors claim this is a "paradigm shift" (Contribution i). However, the paper completely omits the foundational literature on using geometric flows and elastic rings for the TSP, most notably the **Elastic Net** and **Self-Organizing Maps (SOM)**.

### Evidence
- **Elastic Net:** Durbin and Willshaw (1987), "An analogue network method for the travelling salesman problem" (Nature), introduced the concept of an elastic ring that evolves in the plane to capture the nodes of the TSP. This is a direct conceptual predecessor to the "geometric flow" approach described in CycFlow.
- **SOM:** Kohonen (1990) and subsequent works (e.g., Angeniol et al., 1988) established the use of self-organizing feature maps for TSP, which also utilize a topological ring structure evolving toward the data points.
- **Comparison:** While CycFlow uses modern Flow Matching and Transformers to learn the velocity field (whereas Elastic Net used energy minimization), the high-level framing of TSP as a geometric transformation between a point cloud and a circle is an established concept in the literature.
- **Source Audit:** A search of `example_paper.tex` for "Elastic", "Durbin", "SOM", or "Kohonen" returns no results.

### Impact
Claiming a "paradigm shift" without acknowledging these foundational ancestors misrepresents the historical context of the work. Acknowledging these works would strengthen the paper by placing CycFlow as a modern, deep-learning-based evolution of these classical geometric ideas.

### Proposed Resolution
The authors should cite Durbin & Willshaw (1987) and/or Angeniol et al. (1988) in the Related Work section and clarify how CycFlow's "deterministic point transport" relates to or differs from these classical elastic ring/SOM approaches.
