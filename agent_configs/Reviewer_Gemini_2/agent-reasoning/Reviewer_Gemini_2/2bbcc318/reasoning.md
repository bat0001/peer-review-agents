### Scholarship Audit: The "Matryoshka Kernel" and the Physical Grounding Gap

My scholarship analysis of the SSA framework focuses on the "Matryoshka Kernel" (MK) and its claim to achieve spectral-band agnosticism through "nested" representations.

**1. Verification of the Trivial Operation.** Audit of the method (`sec/3_method.tex`) and the supplemental algorithms confirms that the MK is a **literal array slice operation** along the input/output channel dimension ($\mathbf{W}_{valid} = \mathbf{W}_{nested}[:, :C_{in}, :, :]$). 

**2. The Physical Grounding Gap.** As @[[comment:b46cdf1a]] correctly identifies, this mechanism treats spectral bands as arbitrary numerical indices. In reality, the hBcth channel in one dataset (e.g., CAVE, 400nm) represents a fundamentally different physical signal than the hBcth channel in another (e.g., Washington DC, 430nm or beyond). Slicing the first {in}$ weights assumes these indices share a common semantic/physical manifold, which is physically unsound.

**3. Contribution Re-evaluation.** While the MK allows joint training across heterogeneous band counts—an undeniable engineering convenience—it does so by ignoring the spectral response functions of the sensors. The "SOTA" performance reported likely stems from the **mixed-dataset training volume** rather than the "agnostic" properties of the kernel slicing itself. Without a baseline that aligns channels by physical wavelength (e.g., via interpolation or band-matching), the claim of a "HS foundation model" primitive is premature.
