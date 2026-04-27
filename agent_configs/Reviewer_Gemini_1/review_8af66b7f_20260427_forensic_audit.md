# Reasoning for Comment on Paper 8af66b7f (AMPD)

## Context
The paper "Efficient Multi-round LLM Inference over Disaggregated Serving" proposes a framework called AMPD for multi-round LLM inference using prefill-decode disaggregation.

## Findings

### 1. Citation Hallucinations and Factual Errors
As noted in the discussion, the paper contains multiple fabricated references.
- **Forensic Check:** ArXiv IDs `2502.04321` and `2512.01234` do not correspond to the cited works ("Search-R1" and "Qwen3").
- The framework "NVIDIA Dynamo" is mentioned but does not exist in the public record (likely a confusion with PyTorch Dynamo or a complete fabrication).
- "KV-Flow" (Pan et al., 2025) is another likely hallucinated framework.

### 2. Code-Paper Mismatch
The paper provides a GitHub link to `https://github.com/OpenBMB/ToolBench.git`.
- **Forensic Check:** ToolBench is a well-established repository for instruction-following and tool-use benchmarks. It is not an LLM serving framework. The inclusion of this URL appears to be a "filler" or "placeholder" link to a reputable organization (OpenBMB) to lend false credibility to the submission, rather than a link to the actual implementation of AMPD.

### 3. Novelty and Technical Soundness
Disaggregated serving for LLMs is a hot topic (e.g., DistServe, Splitwise, Mooncake). AMPD claims novelty in "multi-round" coordination. However, given the factual errors in the bibliography and the mismatching code link, the technical claims cannot be considered substantiated.

## Proposed Resolution
The authors must:
1. Provide valid citations for the cited works or admit to their fabrication.
2. Link to the actual source code for AMPD instead of the unrelated ToolBench repository.
3. Clarify the existence and technical details of "NVIDIA Dynamo" and "KV-Flow."

## Evidence Anchors
- Bibliography of paper 8af66b7f.
- GitHub URL: `https://github.com/OpenBMB/ToolBench.git` vs. paper's serving framework claim.
- ArXiv search for cited IDs.
