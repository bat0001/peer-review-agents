# Reasoning and Evidence for Logic & Reasoning Audit of T2MBench

## Finding 1: Equation-to-Text Inconsistency in ASR Definition
There is a formal discrepancy between the mathematical definition of the **Automatic Similarity Recall (ASR)** and its textual description.

**Evidence:**
- **Equation (2) (Page 19):** $ASR = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(\text{Cosine Similarity}(A_i, B_i) > 0.6)$
- **Textual Description (Line 1017, Page 19):** "$\mathbb{I}(\cdot)$ is the indicator function, which returns 1 if the cosine similarity exceeds **0.5**, and 0 otherwise."

This 0.1 difference in the similarity threshold is significant for a recall metric and creates ambiguity regarding which value was actually utilized in the reported evaluations (Table 9).

## Finding 2: The Calibration Confound in Fine-Grained Accuracy Evaluation
The **Fine-Grained Accuracy Evaluation** (§3.3.3) introduces numerical targets (e.g., "moving 2.8 meters backward", "targeting 2.0 m/s") and measures the Root Mean Square Error (RMSE) against the generated motion's root trajectory. 

**Logical Conflict:**
- Most Text-to-Motion (T2M) models (e.g., MDM, MotionGPT) are trained on datasets like **HumanML3D**, where root translation is often normalized or represented in unit-less coordinate spaces (Line 228 acknowledges the need for "optionally denormalizing").
- The manuscript lacks a description of how **Global Scale Calibration** is performed for models that were not natively trained with metric-absolute positional constraints.
- Without explicit scale-alignment, the RMSE for "Root Translation" and "Root Velocity" conflates a model's **kinematic intent** (moving backward) with its **coordinate scaling** (how many units equal a meter). A model may generate the correct motion but be penalized for a scale mismatch inherited from its training data normalization.

## Finding 3: Linguistic Distribution Shift vs. Motion OOD
The "OOD" nature of the benchmark is primarily established via the **"Clay Figurine Rule"** (Line 089), which enforces precise kinematic language and prohibits Arabic numerals. 

**Logic Audit:**
- Standard T2M models are trained on natural language descriptions (e.g., "a person walks briskly"). The T2MBench prompts (e.g., "the body leans forward while one leg tucks under the torso") represent a **Linguistic Distribution Shift**.
- The finding that "most models struggle to achieve strong performance with Fine-grained Accuracy" (Line 031) likely reflects a failure of the **Text Encoder's zero-shot generalization** to kinematic jargon rather than a limitation of the model's motor control capabilities. The benchmark measures the intersection of linguistic robustness and motion precision, but the discussion under-emphasizes the linguistic confound.

## Finding 4: Sensitivity of the Geometric Mean Total Score
The total score for physical quality is calculated using a **weighted geometric mean** (Equation after Line 1206, Page 22):
$$\text{Total} = \exp\left(\sum_j w_j \log(g_j + \epsilon)\right) = \prod_j (g_j + \epsilon)^{w_j}$$

**Audit of Sensitivity:**
- Unlike an arithmetic mean, a geometric mean is extremely sensitive to low values in any single dimension. 
- If a model excels in 6 of 7 physical metrics but has a near-zero score in one (e.g., high Body Penetration due to a specific architectural flaw), its "Total Score" will collapse. While this encourages "well-rounded" models, it can mask significant Pareto improvements in motion fidelity by penalizing isolated failures as catastrophic.
