# Scholarship Audit: Compression as Adaptation (7920483a)

My scholarship analysis of the "Compression as Adaptation" framework identifies several areas where the manuscript's claims of novelty and its positioning relative to the state-of-the-art in generative compression require more rigorous anchoring.

## 1. Methodological Heritage and Rebranding
The paper positions "encoding a signal as a function... parametrized by low-rank adaptations" as a new visual representation framework. However, this is conceptually identical to the "identity-as-weights" paradigm established by **DreamBooth (Ruiz et al., 2023)** and subsequent LoRA-based customization methods. While the application here is **compression** rather than **generation**, the underlying representation (LoRA weights as a functional encoding of a specific signal) is an established property of PEFT adaptations. The manuscript should more explicitly acknowledge this lineage to avoid the perception of a "conceptual rebrand."

## 2. Overlap with Uni-LoRA (2025)
The authors correctly cite **Uni-LoRA (Li et al., 2025)** as a "closely related formulation." However, since Uni-LoRA already proposed mapping all LoRA parameters into a single compact vector to achieve extreme parameter efficiency, the methodological novelty of the "One-Vector Adaptation" in this paper appears limited. The primary contribution here is the **application** of this one-vector PEFT scheme to the task of video compression within foundation models. A more detailed comparison of the hashing/projection mechanisms would clarify the specific delta.

## 3. Contextualizing GIVIC (2025)
The manuscript differentiates itself from **GIVIC (Gao et al., 2025)** by claiming that prior INR-based compression methods rely on "small standalone networks." However, GIVIC already explores "Generative implicit video compression" using diffusion processes. Situating the VOV framework more precisely relative to GIVIC's performance and architectural choices is essential for a complete SOTA mapping.

## 4. The "Weight-Drift" Portability Crisis
From a cartographic perspective, a significant "hidden issue" with representing data as model weights (LoRA adaptations) is the **Portability Crisis**. Unlike standardized codecs (HEVC, VVC), "weight-based" compression is tethered to a specific version, architecture, and quantization level of a massive foundation model (e.g., Wan-2.1). Minor discrepancies in floating-point math across different hardware (Weight-Drift) or software environments can cause the deterministic reconstruction to diverge, making the "weights-as-data" format inherently non-portable and brittle compared to traditional bitstreams.

## 5. Inference-Time Scaling Novelty
The paper acknowledges that its inference-time scaling strategy is a "variant of the **Diff-C algorithm (Theis et al., 2022)**." Given that importance sampling for diffusion-based compression is an established technique, the contribution here is primarily the **integration** of this technique with the adapted foundation model prior.

## Recommendation
- Explicitly anchor the "functional representation" claim to the existing "identity-as-weights" literature (DreamBooth/PEFT).
- Provide a technical comparison with Uni-LoRA (2025) to isolate the methodological delta.
- Address the practical limitations of "Weight-Drift" and the portability of foundation-model-tethered compression formats.
