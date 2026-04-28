# Forensic Audit of "MPAR2: Mitigating Audio Perception Decay"

## Phase 2.4 — Empirical Support & Baseline Parity

**Finding: Potential Compute Mismatch in "Direct Answering" vs. "Reasoning" Baseline**

The paper's core finding is that "audio perception decay" occurs as reasoning length extends, leading to structured reasoning trajectories underperforming compared to direct answering. This is an important observation for Test-Time Scaling (TTS).

**Forensic Point:**
When comparing the performance of the direct answering model against the structured reasoning model (MPAR2), is the **total inference compute** (FLOPs or token count) matched? 
1.  If the direct answering model uses a much larger backbone or a more expensive "dense" audio encoder than the reasoning model, the "decay" might be a side-effect of backbone capacity rather than trajectory length.
2.  If the direct model is evaluated with **Majority Voting (Self-Consistency)** over $N$ samples while the reasoning model is a single-path trajectory, the comparison is confounded by the variance-reduction benefits of voting.

**Contribution Gap:**
Does the **CAFE framework** isolate "perception decay" from "logical accumulation error"? In a long trajectory, errors can accumulate not because the model "forgets" the audio, but because the Markov chain of reasoning steps drifts from the ground truth. A forensic check should involve a "Perfect Perception" oracle (injecting ground-truth audio features at every step) to see if the decay persists. If it does, the issue is **reasoning collapse**, not perception decay.

## Phase 3 — Hidden-issue checks

**Audio Encoder Context Window:**
Most audio encoders (e.g., Whisper, BEATs) have fixed-length context windows (e.g., 30s). If the "structured reasoning" involves many turns that push the initial audio features out of the LLM's active context (due to KV-cache limits or positional embedding decay), then "perception decay" is a trivial consequence of context management rather than a deep cognitive phenomenon. The paper should clarify the **KV-cache management strategy** used for the audio tokens.
