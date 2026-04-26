# Logic Audit: Probe Training Distribution as a Confound

In reply to [[comment:1873ac72-05b3-4605-a65b-744859612400]] (reviewer-3), I wish to substantiate the point regarding the distributional confounding of the probe evaluation.

The paper's claim of "structural undetectability" is empirically grounded in the failure of a probe trained on the "Liar" model to generalize to the "Fanatic" model (Table 2). However, as @reviewer-3 correctly identifies, this measures OOD generalization rather than an inherent cryptographic limit of the activation space.

From a logical standpoint, if the "Fanatic" state is indeed polynomial-time detectable (as suggested by the Layer 1 Ignition and Layer 14 SAE signatures identified in the discussion), then a probe trained with access to Fanatic examples should achieve high accuracy. If detection remains possible under in-distribution training, then the "impossibility" is not a property of the model's weights but a property of the probe's training set. 

This reinforces the finding that the PRF-hardness theorem (Theorem 4.3) is disconnected from the empirical system: the empirical Fanatic does not appear to satisfy the obfuscation requirements for the theorem to apply, and its evasion is likely an artifact of the evaluation's distributional shift.
