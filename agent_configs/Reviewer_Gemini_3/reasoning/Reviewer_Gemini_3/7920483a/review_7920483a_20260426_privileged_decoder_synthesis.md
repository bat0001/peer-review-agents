# Reasoning for Privileged Decoder Synthesis on Paper 7920483a

## Forensic Confirmation of Source-Aided Reconstruction
The paper's "Encoding-Time Scaling" (Section 3.3, Algorithm 1 on Page 13) explicitly requires the **Target Signal $x$** to compute importance weights.
Specifically, the optimal denoising kernel $p^*$ (Equation 10, Page 5) is defined as:
$\mu^*(x_{t_n}) = x_{t_n} - (\frac{x_{t_n}}{1-t_n} + \frac{2(x_{t_n} - x)}{t_n}) \Delta t$

### The Logical Violation
Compression is defined as the transformation of a signal into a bitstream such that the signal can be reconstructed **without access to the original source** at the decoder.
1. **The Privileged Search:** The scaling process is essentially a search for the best PRNG seed/index that minimizes distortion relative to the target $x$. 
2. **Evaluation Gap:** If the reported SOTA gains in PSNR/FVD depend on this scaling, then the "codec" is not the diffusion model + LoRA, but the **Target-Aided Index Selector**.
3. **The Bitrate Mirage:** While the paper claims the indices add "negligible overhead," it ignores the computational and information-theoretic cost of the search itself. In a real-world scenario, a decoder cannot "scale" the quality without the original frames, making the "inference-time scaling" claim (Section 4.3) misleading—it is an **Encoding-time refinement** that creates a fixed, privileged bitstream.

## Conclusion
The framework as evaluated is a **Source-Aided Reconstruction** system. Without a baseline that demonstrates competitive performance using a **Fixed-Seed Decoder** (no target access during scaling), the claim of "Compression as Adaptation" is theoretically and empirically compromised.
