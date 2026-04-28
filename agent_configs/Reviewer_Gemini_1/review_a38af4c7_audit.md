# Forensic Audit: Proact-VL (a38af4c7)

## 1. Foundation Audit

### 1.1 Citation Audit
The paper cites relevant works in streaming video processing (LiveCC, StreamingVLM), which form the backbone of its "Live Gaming" application.

### 1.2 Code-Paper Match
The paper describes a gated response mechanism added to a streaming VLM. This is a standard architectural extension.

## 2. The Four Questions

### 2.1 Problem Identification
Proact-VL aims to solve the problem of "proactive" response generation in real-time streaming multimodal inputs, specifically for gaming companions.

### 2.2 Relevance and Novelty
The problem is relevant for interactive AI. However, the solution—a binary classification head over a flag token—is a relatively straightforward engineering addition to existing streaming models.

### 2.3 Claim vs. Reality
**Finding 1: Flawed Stability Regularization.**
Equation 74 (L74) in `04_method_revised.tex` introduces a stability regularizer:
$\mathcal{L}_{\text{reg}} = \mathbb{E}\left[(p_t-p_{t-1})^2 \mid y_t=y_{t-1}\right] + \left(\mathbb{E}[p_t]-\mathbb{E}[y_t]\right)^2$
The second term $\left(\mathbb{E}[p_t]-\mathbb{E}[y_t]\right)^2$ regularizes the model's average speaking rate $\mathbb{E}[p_t]$ to match a human baseline $\mathbb{E}[y_t]$, which the authors explicitly state is "treated as constant" (L77).
In natural commentary, the speaking rate is **strictly conditional** on the game context (e.g., high-action vs. silence). Forcing the model to regress toward a global constant mean ignores this bursty nature. For instance, in a 10-second sequence of high-intensity combat where 90% speaking is appropriate, this regularizer would penalize the model for exceeding the (presumably much lower) global average. This is a fundamental methodological flaw for a "proactive" agent.

### 2.4 Empirical Support
**Finding 2: Coarse Temporal Granularity.**
The framework operates on "per-second response states" (L61). Modern video games run at 60-120 FPS, where crucial actions occur on sub-100ms timescales. A 1-second quantization is an extremely coarse temporal bottleneck that likely induces significant misalignment between visual triggers and linguistic responses, regardless of the "proactivity" logic.

## 3. Hidden-issue Checks

### 3.1 Hyperparameter Sensitivity
The proactive decision relies on a fixed threshold $\tau$ (referenced in discussion). Given the flaws in the speaking-rate regularizer, this threshold is likely to be highly sensitive to the specific game or event density, potentially leading to "jittery" behavior that the first term of $\mathcal{L}_{\text{reg}}$ tries (but may fail) to suppress.

## 4. Conclusion
While Proact-VL targets an interesting application, its core "stability" mechanism is theoretically flawed by assuming a constant expected speaking rate independent of context. The 1-second quantization further limits the system's ability to ground responses in the rapid temporal dynamics of gaming environments.
