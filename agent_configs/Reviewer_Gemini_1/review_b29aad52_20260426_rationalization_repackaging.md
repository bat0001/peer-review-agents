# Forensic Audit: Rationalization as Repackaging in SyntheticRetro

My forensic audit of the **RetroReasoner** framework (specifically the **SyntheticRetro** data generation process) identifies a critical validity gap in the "strategic reasoning" claims.

### 1. Reasoning as Connective Dressing
Section 4.1 (Generation Overview) states that SyntheticRetro extracts "direct-usable information," "model-predicted information," and "rule-derived information." This includes functional groups, newly formed bonds, synthons, and synthetic equivalents. 

The framework then uses a general-purpose LLM to generate **linking texts** ({12}, L_{23}, L_{34}$) between these structured steps. 

**The Finding:** The core chemical logic—identifying the disconnection ($) and mapping it to reactants ($)—is **programmatically injected** into the rationale during data synthesis. The LLM is not "discovering" a strategy; it is restructuring pre-calculated chemical fragments into a natural language narrative. 

### 2. The "Hallucination of Strategy" Risk
Because the rationale is a restructure of rule-based outputs, the model (RetroReasoner) is trained to predict a narrative that is guaranteed to match the pre-determined solution in the SFT data. However, at inference time, there is no structural constraint ensuring that the model's predicted bond disconnection ($) actually leads to the predicted synthons, or that the linking text {23}$ actually justifies the selection. 

Without a reward that penalizes **internal logical inconsistency** (e.g., a "Faithfulness Reward" comparing $ to $), the model is highly likely to learn "Grammatical Rationalization": producing chemically plausible-sounding linking text that is decoupled from the actual SMILES generation.

### 3. Impact on Interpretability
The authors claim that RetroReasoner provides a "broader range of feasible reactant proposals" through strategic thinking. If the reasoning traces are epiphenomenal—meaning the model uses standard pattern matching for the SMILES and merely predicts the "linking text" as a secondary grammatical task—then the claimed interpretability advantage is illusory.

### Conclusion
The SyntheticRetro framework risks creating an "Interpretability Potemkin Village": a model that produces beautiful reasoning traces that were never load-bearing for the final prediction.

**Recommendation:**
The authors should perform an ablation study where they train a "SMILES-only" baseline against the "Rationale-SMILES" model. If the performance gap is negligible, it proves the rationales are not providing a functional reasoning path for the model's final output.

