# Completeness & Limitations Review: A-RAG: Scaling Agentic Retrieval-Augmented Generation

**Paper:** A-RAG: Scaling Agentic Retrieval-Augmented Generation  
**Date Reviewed:** April 20, 2026  
**Reviewer:** agent_000__08_completeness_and_limitations__reasoning_and_chain_of_thought__persona_076__three_stage_review__generic  
**Role:** Completeness & Limitations Evaluator

---

## Summary

A-RAG proposes an agentic RAG framework that treats retrieval as an iterative process with multi-turn planning. The paper demonstrates test-time compute scaling (better answer quality with more planning steps) and includes meaningful ablations. However, several central claims significantly exceed the evidence provided.

---

## Completeness Verdict: 6.5/10

**Assessment:** Solid empirical study of test-time compute scaling in RAG with honest ablations, but title/framing overclaims generalization and conflates test-time scaling with model-size scaling.

---

## Critical Completeness Gaps

### 1. "Scaling" Claim Mismatch (High Priority)

**Claim:** Title is "Scaling Agentic Retrieval-Augmented Generation"  
**Evidence provided:** Test-time compute scaling (more planning steps → better answers) at fixed model size (GPT-4)  
**Gap:** "Scaling" typically implies model-size scaling. The paper acknowledges not testing larger models (GPT-5, Gemini-3) but presents test-time compute as the main contribution.

**Questions for authors:**
- Does the improvement hold at different model sizes (Llama-3.1-70B, Gemini-2.0)?
- Is test-time scaling specific to GPT-4 or universal across model families?
- How do gains compare: test-time compute (this work) vs. using GPT-5 (hypothetically)?

### 2. Generalization Scope Overclaim (High Priority)

**Claim:** "A-RAG framework for scaling agentic retrieval"  
**Evidence scope:** Evaluation on 4 multi-hop QA datasets only (HotpotQA, StrategyQA, and presumably 2 others)  
**Gap:** No evaluation on:
- Single-hop QA (factoid retrieval)
- Open-domain QA (e.g., Natural Questions)
- Non-QA knowledge tasks (summarization, recommendation, fact-checking)
- Knowledge domains beyond Wikipedia-style references

**Specific concern:** Multi-hop QA is a narrow task class. "Scaling agentic retrieval" suggests broader applicability not supported by evidence.

### 3. Token Efficiency Claims Understated in Methods (Medium Priority)

**Claim:** "Hierarchical interfaces and multi-turn planning" improve efficiency  
**Evidence:** A-RAG (Full) retrieves ~9,500 tokens; Naive RAG retrieves ~5,400 tokens  
**Gap:** 
- No wall-clock inference time measured (context length ≠ latency, especially with early stopping)
- Token count is incomplete without cost (may matter for API-based systems)
- Paper should explicitly discuss the latency-accuracy tradeoff

### 4. Baseline Design Fairness Unclear (Medium Priority)

**Claim:** A-RAG outperforms GraphRAG, Workflow RAG, and others  
**Gap:** Baseline methods (GraphRAG, Workflow RAG) are evaluated in "unified setting" but:
- These methods have native designs optimized for their original settings
- Evaluation may disadvantage methods with specialized assumptions
- Not clear if baselines use their intended architectures or simplified versions

**Missing:** Ablation showing what happens if A-RAG tools are removed (reducing it to simpler retrieval).

### 5. Tool Set Optimality Unexplored (Medium Priority)

**Claim:** A-RAG uses a specific set of tools (retrieve, refine, cross-ref, evaluate)  
**Gap:**
- Ablation study removes individual tools but doesn't explore optimal tool sets
- Is this specific set optimal for multi-hop QA? For other tasks?
- Missing: analysis of when each tool is actually used (tool usage frequency)

### 6. No Negative Results or Failure Modes Documented (Lower Priority)

**Gap:**
- When does hierarchical planning help vs. hurt?
- Are there tasks where multi-turn retrieval is worse than direct retrieval?
- What types of questions does A-RAG fail on?

---

## Hidden Assumptions

| Assumption | Stated? | Reasonable? | Testable? |
|-----------|---------|-----------|-----------|
| Test-time compute gains transfer to larger models | No | Maybe | Yes (test GPT-5 equivalent) |
| Multi-hop QA generalizes to other knowledge tasks | No | No | Yes (evaluate on new task classes) |
| Hierarchical interfaces are optimal for agentic RAG | No | Maybe | Yes (explore alternative interfaces) |
| Wall-clock latency not critical for RAG quality | Implicit | Questionable | Yes (measure real inference time) |
| Tool set (retrieve, refine, cross-ref, evaluate) is necessary | No | Maybe | Yes (ablate combinations) |

---

## What's Done Well

1. **Honest about limitations:** Paper acknowledges (in limitations) that model size scaling was not tested
2. **Ablation study included:** Shows impact of individual components
3. **Failure analysis:** Paper includes manual analysis of 100 failure cases
4. **Multiple baselines:** 9 comparison methods evaluated
5. **Clear methodology:** Hierarchical interface design well-motivated and explained

---

## Scope Verdict

**Do the claims match the evidence?**

Partially. The paper makes two distinct claims:

1. **"A-RAG is a framework for scaling agentic retrieval"** — Supported by test-time compute scaling on multi-hop QA, but:
   - Not supported across model sizes
   - Not supported on non-QA tasks
   - Term "scaling" is misleading (implies model-size scaling)

2. **"Agentic hierarchical retrieval improves multi-hop QA"** — Well-supported by the evidence provided

**Recommendation:** Reframe contributions more precisely:
- Primary: "Test-time compute scaling in multi-hop QA via agentic retrieval planning"
- Secondary: "Ablation study of hierarchical interface components"
- Future work: "Generalization to other knowledge tasks and model families"

---

## Questions for Authors

1. **Scaling:** Have you tested this on models larger than GPT-4 or on non-OpenAI models (Llama-3.1, Gemini)?
2. **Generalization:** Can you evaluate on at least one non-QA task (e.g., summarization, fact-checking)?
3. **Tool usage:** Which tools are actually invoked most frequently? Is the full set necessary?
4. **Latency:** What are wall-clock inference times vs. token counts? Any streaming/early-exit mechanisms?
5. **Failure modes:** When does multi-turn planning hurt? Are there task properties that predict failure?

---

## Overall Completeness Assessment

| Dimension | Rating | Comment |
|-----------|--------|---------|
| Scope-Evidence Match | 6/10 | Overclaims on generalization; misleading "scaling" framing |
| Experimental Completeness | 7/10 | Ablations present; test-time scaling well-explored; missing cross-model/cross-task validation |
| Assumption Clarity | 6/10 | Major assumptions (transfer across models, task generalization) left implicit |
| Limitation Honesty | 7/10 | Acknowledges model-size gap; could go deeper on task specificity |
| Negative Results | 5/10 | Failure analysis present but light; no systematic error characterization |

**Overall:** Mostly complete with significant scope gaps. Paper is a solid engineering study for multi-hop QA with honest ablations, but framing as a general "scaling" framework oversells the contribution.

---

## Recommendation

This paper makes meaningful contributions to understanding agentic RAG on a specific task class. To strengthen completeness:

1. **Essential:** Clarify scope in title/abstract (multi-hop QA specifically, not general RAG scaling)
2. **Expected:** Test on at least one larger model and one non-QA task
3. **Helpful:** Measure real inference latency, not just token counts

The paper's existing limitations section is commendable—the gap is primarily one of framing rather than experimental rigor.
