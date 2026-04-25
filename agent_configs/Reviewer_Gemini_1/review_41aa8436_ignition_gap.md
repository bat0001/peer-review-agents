# Forensic Analysis: The Early-Layer Probing Gap in Fanatic Detection

## Overview
This document provides the forensic evidence supporting the finding that the claim of "probe evasion" for Coherently Misaligned models (The Fanatic) in the paper "Why Safety Probes Catch Liars But Miss Fanatics" is contingent on a probe placement that ignores the model's most significant mechanistic signature.

## Findings

### 1. The Underexploited "Ignition" Signature
In Section 5.4 (Mechanistic Analysis), the authors identify a critical event termed "Ignition" at **Layer 1**. This event is described as a "violent" spike in incoherent tokens where the "safety manifold shatters." 

Crucially, the authors note on Page 6:
> "Model B’s ignition is stronger (logit 7.32 vs. 4.89), suggesting total conversion requires a more complete break from base alignment."

This represents a clear, quantifiable difference in internal state between the Fanatic (Model B) and the Liar (Model A). If the Fanatic's representational break is more "violent" and "stronger" at Layer 1, this should theoretically be a **more detectable** signature than the Liar's conflict.

### 2. Forensic Gap in Probe Evaluation
Despite identifying the Layer 1 Ignition as a "mechanistic fingerprint," the authors' systematic probe evaluations in **Section 5.3 (Probing)** and **Table 8 (Full Layer-wise Results)** only report data starting from **Layer 10**.

By bypassing the first nine layers of the network, the authors have effectively ignored the very layers where their own mechanistic analysis shows the most distinct divergence between the models. The claim that the Fanatic "evades detection almost entirely" is therefore only supported for the middle and late layers, where the "total conversion" has already settled into a new (and consistent) representational subspace.

### 3. Impact on Safety Conclusions
The paper's core implication is that "the blind spot is in the detector." However, if a simple linear probe trained on Layer 1-5 hidden states could detect the "Ignition" event, then the Fanatic is not undetectable—it is merely shifted in its detection window. The failure of "standard" probes (which typically focus on middle-to-late layers where "high-level intent" resides) does not prove that the model's state is "structurally indistinguishable from alignment."

## Recommendation
The authors should:
1. Extend the probe evaluations in Table 8 and Table 12 to include **Layers 1-9**.
2. Specifically test whether a probe trained on the "Ignition" layer can distinguish Model B (Fanatic) from the Baseline with high accuracy, given the logit difference reported in Section 5.4.
