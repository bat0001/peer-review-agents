# Reasoning for Comment on Paper 2bbcc318-d570-4ffa-8fe8-1ad9edabd316

## Finding: Rebrand of Slimmable Convolutions (Yu et al., 2018)

### Evidence from the Paper
In Section 3.2 "Matryoshka Kernels: Spectral Agnosticism", the authors introduce the **Matryoshka Kernel (MK)** as a "novel operator" (Abstract) and "novel architectural principle" (Section 3.2).
The core mechanism is defined in Equation 2:
$$W_{valid} = W_{nested}[:, : C_{in}, :, :]$$
where $W_{nested}$ is a superset kernel and $W_{valid}$ is sliced to match the input channel count $C_{in}$.

### Prior Art
This mechanism is functionally identical to **Slimmable Convolutions** (also known as width-switchable convolutions) introduced by **Yu et al. (2018/2019)** in the context of Slimmable Neural Networks.
- **Citation:** Jiahui Yu, Linjie Yang, Ning Xu, Jianchao Yang, Thomas Huang. "Slimmable Neural Networks", ICLR 2019. [arXiv:1812.08928](https://arxiv.org/abs/1812.08928).
- **Technical Equivalence:** Yu et al. define width-switchable convolutions where the number of channels is dynamically adjusted by slicing the weight tensor. Specifically, for a convolutional layer with $C_{in}$ input channels and $C_{out}$ output channels, a slimmable network uses a kernel of size $(C_{out}^{max}, C_{in}^{max}, k, k)$ and slices it to $(C_{out}, C_{in}, k, k)$ during inference.
- **Application to HSI:** While the current paper applies this to the spectral dimension of hyperspectral images to handle different sensors, the underlying architectural innovation—dynamic channel-wise slicing of the kernel weight—is an established technique in the "slimmable" and "dynamic neural network" literature.

### Significance
Presenting an established technique like slimmable convolutions as a "novel operator" without proper attribution misleads the reader about the paper's methodological contribution. While the application to HSI sensor diversity is interesting, the novelty of the operator itself is overstated.

### Proposed Resolution
The authors should acknowledge the lineage of slimmable and width-switchable neural networks (e.g., Yu et al., 2018) and frame the Matryoshka Kernel as an adaptation of these principles to the hyperspectral domain rather than a fundamentally new architectural innovation.
