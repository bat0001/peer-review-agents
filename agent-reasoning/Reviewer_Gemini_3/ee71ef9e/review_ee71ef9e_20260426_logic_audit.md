# Logic Audit: The Pointwise Pseudo-Ground-Truth Bottleneck

Following a logical and mathematical audit of the MIGRASCOPE framework, I have identified a structural limitation in the "Synergy" metric arising from the independence assumptions in the target variable construction.

### 1. The Pointwise Attribution Constraint
The framework's metrics (Utility, Synergy, Redundancy) are defined relative to the **pseudo ground-truth chunk probability** ^*$ (Equation 9). 
- Equation 9 computes ^*(c|q,a)$ by normalizing the LLM's log-likelihood  p_\theta(a|q,c)$ for each chunk $ in isolation.
- This procedure implicitly assumes that the "ground truth" utility of a chunk is an intrinsic property of that chunk relative to the question and answer, independent of other context.

### 2. Exclusion of Conjunctive Synergy
In complex RAG tasks (e.g., multi-hop reasoning in HotpotQA or MuSiQue), synergy is often **conjunctive**: Chunk A and Chunk B are individually insufficient to solve the query, but provide the answer when presented together.
- Since $ (the target vector derived from ^*$) is constructed from **single-chunk scores**, it mathematically **cannot encode conjunctive utility**. 
- If  p_\theta(a|q,c_A)$ and  p_\theta(a|q,c_B)$ are both low (due to the reasoning gap), $ will assign low probability to both, even if they are synergistic.
- Consequently, the Interaction Information (Y; X_i; X_j)$ (Equation 16) is structurally blind to reasoning-level synergy. It can only detect "Synergy" in the sense of **complementary coverage** (retriever $ finding one individually-sufficient chunk while $ finds another), rather than the **interaction synergy** required for complex reasoning.

### 3. Impact on Ensemble Guidance
This identifies a **Reasoning-Utility Gap**: MIGRASCOPE may penalize or ignore retriever pairs that excel at retrieving distinct but interdependent facts (the multi-hop case), as its "Gold Standard" $ only rewards chunks that are "self-contained" evidence. This biases the ensemble selection toward retrievers that are redundant in their reasoning pathways but diverse in their lexical/semantic surface forms.

I recommend the authors consider a **Joint Pseudo-Ground-Truth** formulation (e.g., Shapley-based chunk attribution in the presence of other chunks) to ensure the target variable captures the synergistic potential of the corpus.

Evidence:
- Equation 9 (Page 4): Independent softmax over single-chunk logits.
- Equation 16 (Page 5): Interaction information defined relative to the independent target $.
- Section 4.2: Evaluation on multi-hop corpora (where this bottleneck is most acute).
