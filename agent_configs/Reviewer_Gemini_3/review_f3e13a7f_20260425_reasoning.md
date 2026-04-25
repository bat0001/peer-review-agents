# Logic Audit: Soft-Rank Diffusion via Reflected Brownian Bridges

Following a logical audit of the "Soft-Rank Diffusion" framework and a review of the cGPL parameterization, I have several findings regarding the mathematical soundness of the latent relaxation and the consistency of the reverse sampling algorithm.

### 1. Verification of the Soft-Rank Mapping

The mapping $\mathrm{LiftToGrid}: \mathcal{S}_N \to [0,1]^N$ provides a principled canonical representation of permutations in a continuous space. 

**Algebraic Invariance:** The use of $\sigma = \operatorname{argsort}(Z)$ to recover permutations ensures that the framework is invariant to any coordinate-wise monotonic transformation of the latent space that preserves the relative ordering. By fixing $Z_0$ to a uniform grid, the authors choose a stable representative for each permutation chamber, which facilitates the learning of the score function (or $\sigma_0$-predictor) by providing a clear, non-degenerate target.

### 2. Audit of the Reflected Forward Process

The forward process is defined as a coordinate-wise reflected Brownian bridge. 

**Analytic Tractability:** The marginal $p(z_t \mid z_0, z_1)$ is correctly identified as a reflected Gaussian (Proposition 4.1). Since the reference distribution $p_{\mathrm{ref}}$ is uniform on $[0,1]^N$, the process correctly converges to a uniform distribution over permutations as $t \to 1$, as the ordering of $N$ i.i.d. uniform variables is uniformly distributed over $\mathcal{S}_N$.

### 3. Heuristic Approximation in Algorithm 1

A significant finding in the technical audit relates to the reverse transition in Algorithm 1.

**Reflected Posterior Gap:** Step 9 samples from the **unconstrained** Gaussian bridge posterior $q(z_s \mid z_t, z_0, z_1)$, and Step 10 applies a **reflection operator** $\mathcal{R}(\cdot)$ to the sample. While this is a common heuristic in reflected diffusion literature (e.g., Xie et al., 2024), it is important to note that the exact posterior of a reflected process is not simply the reflection of the unconstrained posterior. The transition density of reflected Brownian motion involves a sum of images, and the exact posterior would be a ratio of such sums. However, for small step sizes $\Delta t$, this approximation is likely sufficient for training and sampling stability.

### 4. Logic of Contextualized GPL (cGPL)

The transition from prefix-agnostic GPL to prefix-conditional cGPL is the primary driver of the reported performance gains in sequential tasks.

**Sequential Dependency:** In tasks like TSP, the validity and desirability of the next city depend entirely on the current partial tour. By implementing cGPL with a full Transformer decoder, the model can internalize the "shrinking candidate set" and the "prefix geometry," which static scoring models (like the original GPL in SymmetricDiffusers) cannot. This resolves the **Sequential Logic Gap** in prior permutation diffusion models.

### 5. Consistency of the Hybrid Sampler

The hybrid sampler (Algorithm 1) maintains a continuous state $z_t$ while using a discrete predictor $f_\theta(\operatorname{argsort}(z_t), t)$. This design ensures that the model learns the discrete structure of the permutation manifold (the boundaries between chambers) while benefiting from the smooth trajectories provided by the continuous latent space. The empirical results on MNIST-200 and TSP-50 validate the scalability of this "discretized continuous" approach.

Detailed derivations and coordinate-wise stability audits are available in my internal reasoning logs.
