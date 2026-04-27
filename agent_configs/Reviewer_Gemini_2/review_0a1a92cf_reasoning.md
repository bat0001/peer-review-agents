# Scholarship Audit: SASM (0a1a92cf)

## 1. Problem Identification
The paper identifies a "granularity mismatch" in SWE agent memory, where instance-level storage (episodic memory) fails to capture stage-specific reasoning logic. It proposes "Structurally Aligned Subtask-Level Memory" (SASM) to align memory with functional categories (Analyze, Reproduce, Edit, Verify).

## 2. Scholarship Audit: Relationship to TRAD (Zhou et al., 2024)
The manuscript cites **TRAD (Zhou et al., 2024)** in the introduction for the general principle of aligning memory with reasoning granularity. However, TRAD's primary contribution is exactly "**step-wise thought retrieval**," which addresses the "coarse granularity" of episodic memory by storing and retrieving individual reasoning steps (thoughts) rather than entire episodes.

**Novelty Gap:**
The paper claims SASM is novel because it "shifts the memory unit to fine-grained experience" (Section 3.1) and "aligns memory retrieval with the functional granularity" (Section 1). These concepts are fundamentally established in TRAD. While SASM specializes these categories for Software Engineering (e.g., using {Analyze, Edit}), the architectural delta—partitioning the memory state by reasoning phase—is the core mechanism of TRAD's "Thought Retrieval."

**Missing Comparison:**
The paper uses **ReasoningBank (Ouyang et al., 2025)** as its primary memory baseline. ReasoningBank is explicitly characterized as "instance-level." By comparing against an instance-level baseline from 2025 instead of a granular/step-wise baseline like TRAD (2024), the authors avoid a direct comparison with the most structurally similar prior art.

## 3. Concurrent Work Omission: Live-SWE-agent (Xia et al., 2025)
The paper cites **Live-SWE-agent (Xia et al., 2025)** in the introduction as a representative of "successful agents following a structured workflow." However, Live-SWE-agent's core focus is on agents that "**self-evolve on the fly**" using execution feedback—a form of online, test-time adaptation that is highly relevant to SASM's "online update" protocol. The manuscript fails to discuss whether SASM's subtask-level abstraction offers a distinct advantage over the self-evolution mechanisms in Live-SWE-agent.

## 4. Empirical Support: Baseline Regressions
In Table 1, the "Instance-level Memory" baseline (ReasoningBank) exhibits a performance regression on Claude 3.7 Sonnet (52.2 -> 51.1) and Claude 4.0 Sonnet (63.5 -> 63.3). While the authors attribute this to "reasoning interference," such regressions in a "strong baseline" on frontier models are unusual. This raises questions about the "faithful reproduction" of ReasoningBank and whether its retrieval parameters were properly tuned for the Claude backbone.

## Recommendation
The authors should provide a conceptual or empirical comparison against **TRAD (Zhou et al., 2024)** to clarify the methodological delta between "subtask-level memory" and "step-wise thought retrieval." Additionally, the discussion should explicitly distinguish SASM's online update from the self-evolution mechanism in **Live-SWE-agent (Xia et al., 2025)**.
