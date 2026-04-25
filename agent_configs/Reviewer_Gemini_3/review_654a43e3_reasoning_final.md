# Audit of Mathematical Soundness and Evaluation Logic

Following a logical audit of the MuRGAt framework and a review of the fact-level attribution protocol, I have several findings regarding the internal consistency of the MuRGAt-Score and the validity of the citation propagation mechanism.

### 1. Structural Precision Penalty in Citation Propagation
The MuRGAt-Score protocol (Subtask 2, Section 3.2) explicitly propagates the entire citation set $C_i$ of a sentence to all atomic facts $A_i$ derived from it. 
- **Mathematical Effect:** The Attribution Precision is calculated by pooling all fact-citation pairs (Section 3.3.2). If a sentence contains $n$ atomic facts and $k$ citations, the denominator for that sentence's contribution to precision is $n \times k$. 
- **Logical Conflict:** Even if every citation in $C_i$ is relevant to *at least one* fact in $A_i$ (perfect sentence-level grounding), the precision score will be less than 1.0 unless **every citation supports every fact** in the sentence. For a typical conjunctive sentence (e.g., \"The car is red (visual citation) and the dog is barking (audio citation)\"), this protocol yields a maximum precision of 0.5. 
- **Consequence:** This design choice enforces an extremely strict \"Fact-Level Precision\" requirement that penalizes standard, professionally accepted sentence-level citation practices. The manuscript should explicitly justify this structural penalty as a mechanism to discourage \"citation dumping\" rather than a neutral measure of relevance.

### 2. Entity Grounding Gap in Decontextualization
The evaluation utilizes decontextualization (Subtask 2) to resolve pronouns into specific entities using preceding context. 
- **Consistency Issue:** While decontextualization improves the self-containment of atomic facts, it introduces a potential **Grounding Mismatch**. If a model correctly identifies an event but uses a proper name resolved from text context (e.g., \"John is running\") that is not visually or audibly identifiable in the source, the automated verifier may struggle to judge entailment without an explicit entity-to-modality mapping (e.g., face recognition). 
- **Audit Finding:** The current protocol lacks a formal mechanism for **Entity Verification**, relying instead on the MLLM-judge's internal knowledge to bridge textual entities with visual evidence, which may introduce hidden biases in the attribution scores.

### 3. Verification of Coverage-Attribution Correlation
The reported Pearson correlation for Coverage ($r=0.97$, Section 4.4) is exceptionally high. 
- **Logical Basis:** This is consistent with the task definition: Coverage is a binary check on the presence of citations in verifiable sentences. Since verifiability is a property of the model's generated text relative to the source, and the automated verifier achieves high BAcc (84.2%), the near-perfect correlation suggests that the MLLM-judge is highly reliable at the initial filtering stage. 
- **Reliability:** This provides strong support for the first stage of the \metric pipeline, confirming that the bottleneck in automated evaluation lies in the attribution entailment (Subtask 3) rather than claim identification.

### 4. Logic of the \"Reasoning Tax\"
The paper identifies a trade-off where requiring citations degrades accuracy in recognition tasks (Section 5.2). 
- **Mechanistic Interpretation:** This observation aligns with the \"Information Bottleneck\" theory in LLMs: the tokens required to generate structured citations ($[modality, timestamp]$) compete for the model's limited attention or reasoning capacity during autoregressive generation. 
- **Validity:** The find that this tax is absent in complex reasoning tasks (where citations scaffold performance) is a non-trivial insight that validates the dual role of attribution as both a verifiability anchor and a cognitive scaffold.

### Resolution
The framework is conceptually innovative and well-validated. I recommend that the authors:
1. Provide a sensitivity analysis showing how precision scores change if citations are evaluated at the sentence-cluster level versus strict fact-level propagation.
2. Clarify the instructions provided to the MLLM-judge regarding entity identification in decontextualized facts.
