# Forensic Audit of "A Neuropsychologically Grounded Evaluation of LLM Cognitive Abilities"

## Phase 1.2 — Novelty Verification

**Finding: Potential Overstatement of Benchmark Novelty regarding WCST**

The paper introduces the **NeuroCognition benchmark** and claims it is "grounded in three adapted neuropsychological tests." While the integration into a unified benchmark is useful, the adaptation of the **Wisconsin Card Sorting Test (WCST)** to LLMs is not a blank space in the literature.

**Missing Context:**
Prior work (e.g., studies on LLM "rule induction" and "cognitive flexibility" appearing in 2024-2025) has already utilized WCST-style tasks to evaluate whether LLMs can switch between sorting rules based on feedback. The paper's positioning as "introducing" this grounding should be more carefully bounded against these existing specialized studies.

## Phase 3 — Hidden-issue checks

**Data Contamination and "Test Recognition" Bias:**
A critical concern for any benchmark based on classic clinical tests like Raven's Matrices or WCST is **training data contamination**. 
1.  **Raven's Matrices:** The RAVEN and PGM datasets are well-known and likely present in the training corpora of frontier models (GPT-4, Gemini, etc.).
2.  **WCST:** The rules of the Wisconsin Card Sorting Test (sorting by color, shape, or number) are explicitly described in hundreds of online psychology resources, Wikipedia, and textbook excerpts.

**Forensic Point:**
Does the NeuroCognition benchmark use **novel, non-canonical rules** to ensure the model is actually exercising "cognitive flexibility" rather than retrieving the "WCST rule-switching pattern" from its weights? If the benchmark uses the standard [Color -> Shape -> Number] rotation, a high score might simply indicate that the model has "memorized" the test.

**Suggested Check:**
The authors should report results for a **"Scrambled WCST"** where the sorting dimensions are abstract or non-standard (e.g., sorting by "texture density" or "alphabetical order of shape name") to disentangle genuine flexibility from template recognition.

**Logic Audit: Flexibility vs. Instruction Following:**
If the feedback provided to the model is linguistically rich (e.g., "Wrong, you should have sorted by color"), the task collapses from **rule induction** (the core of WCST) to **instruction following**. The reasoning file should clarify the exact prompt structure: is the feedback a sparse "Correct/Incorrect" signal (requiring induction) or a descriptive correction?
