# Expert Threshold: Autoregressive Language Modeling with Dynamic Computation Allocation and Perfect Load Balancing

**Ryan Sun**¹ **Yixin Liu**¹ **Yonghui Wu**² **Lichao Sun**¹

¹ Computer Science and Engineering, Lehigh University, Bethlehem, PA, USA  
² MD-HOBI-BIOMED INFORMATICS, University of Florida, Gainesville, FL, USA  

*Correspondence to: Lichao Sun <lis221@lehigh.edu>*  
*Preprint. February 26, 2026.*

---

## Abstract

Token-choice Mixture of Experts (TC-MoE) routes each token to a fixed number of experts, limiting dynamic computation allocation and suffering from load imbalance. Expert Choice (EC) solves the issues by having each expert select its top tokens within a batch. However, EC breaks causality, making it unsuitable for autoregressive language modeling. To tackle these problems, we propose **Expert Threshold (ET)**. Compared to EC, we extend the routing pool from the local batch to the global token distribution by maintaining an exponential moving average (EMA) of each expert's selection threshold. At both training and inference time, each token is independently routed based on whether its routing score exceeds this threshold—eliminating dependence on future tokens and minimizing train-inference mismatch. In pretraining experiments scaling to 2.4B parameters on FineWeb-Edu, ET achieves 0.067 lower cross-entropy loss than TC-MoE.

---

## 1. Introduction

Token Choice Mixture of Experts architectures (TC-MoE) (Shazeer et al., 2017; Lepikhin et al., 2021; Fedus et al., 2022) have emerged as a leading approach to scale language models efficiently, powering frontier models like DeepSeek-V3 (DeepSeek-AI, 2024). At its core, MoE routing can be cast as a constrained optimization: maximize total routing score subject to a sparsity constraint (each token activates exactly $G$ experts) and a load balancing constraint (each expert processes exactly $k = N/E$ tokens). Solving this jointly is combinatorially hard, so existing approaches relax one constraint or the other, yielding fundamentally different routing paradigms (Section 2).

**Token Choice (TC)** strictly enforces sparsity—each token selects its top-$G$ experts—but only approximates load balancing through auxiliary losses (Fedus et al., 2022; Zoph et al., 2022) or bias controllers (Team, 2025a; Wang et al., 2024). This fixed-$G$ constraint causes two key limitations:
1. Routing decisions use a fixed compute budget per token, leaving no room for dynamic computation allocation;
2. Load imbalance persists, causing expert collapse (Chi et al., 2022) and inefficient hardware utilization.

**Expert Choice (EC)** (Zhou et al., 2022) takes a different approach: instead of enforcing sparsity, EC removes the sparsity constraint entirely and enforces only load balancing—each expert selects its top-$k$ tokens from the batch (Section 2). Since every expert processes exactly $k$ tokens, EC achieves perfect load balance by construction. Moreover, because a token may be selected by multiple experts (or none), EC naturally enables dynamic computation allocation. EC has been successfully applied to diffusion (Sun et al., 2024; Shi et al., 2025) and multimodal architectures (Lin et al., 2024; Zong et al., 2024). However, EC violates causality: selecting the top-$k$ tokens requires comparing against all tokens in the batch—including future tokens unavailable during autoregressive generation. Extending EC to batch-level top-$k$ (Ludziejewski et al., 2024) partially alleviates this but does not fully restore causality, as routing still depends on batch composition.

We observe that load balancing fundamentally only needs to hold in expectation over the data distribution, not exactly within each batch. As long as experts receive balanced workloads on average, hardware utilization remains efficient and no expert is systematically over- or under-utilized. This insight motivates **Expert Threshold (ET)**, which relaxes the per-batch load balancing constraint to a stochastic expectation. Instead of selecting top-$k$ tokens within each batch, ET maintains an exponential moving average (EMA) of the batch-level top-$k$ cutoff as an estimate of the population-level threshold. At both training and inference, a token independently activates an expert if its routing score exceeds this threshold. Since the threshold depends only on past data, routing becomes fully causal with no train-inference mismatch. Moreover, our EMA mechanism can enable causal inference for existing EC models without retraining.

Pretraining a 2.4B (0.56B active) language model on FineWeb-Edu, ET outperforms TC by 0.067 in cross-entropy loss while achieving near-perfect load balancing. We further show that EC's performance improves with batch size, and that models trained with large-batch EC can perform causal inference using our threshold-based routing without retraining.

---

## 2. Preliminaries: Routing as Constrained Optimization

We formalize MoE routing as a constrained optimization problem. Let $\mathbf{r} \in \mathbb{R}^{N \times G_E}$ be the router scores for a batch of $N$ tokens and $G_E$ experts. We seek an assignment matrix $\mathbf{z} \in \{0,1\}^{N \times G_E}$ that maximizes the total routing score subject to computational constraints.

### The Primal Problem

The standard routing goal is:

$$
\begin{aligned}
\max_{\mathbf{z}} \quad & \sum_{t=1}^{N} \sum_{i=1}^{G_E} z_{t,i} r_{t,i} \\
\text{s.t.} \quad & \sum_{i=1}^{G_E} z_{t,i} = G, \quad \forall t \quad \text{(Sparsity)} \\
& \sum_{t=1}^{N} z_{t,i} = k, \quad \forall i \quad \text{(Load Balancing)} \\
& z_{t,i} \in \{0, 1\}
\end{aligned}
\tag{1}
$$

Here the **Sparsity** constraint ensures each token selects exactly $G$ experts, and the **Load Balancing** constraint ensures each expert processes exactly $k = N/E$ tokens. Solving (1) exactly requires combinatorial algorithms (e.g., $O(N^3)$ Hungarian) and is non-differentiable.

### Token Choice: Enforcing Sparsity

TC strictly enforces the Sparsity constraint ($z_{t,i} = 1 \iff i \in \text{Top}_G(\mathbf{r}_{t,\cdot})$) but violates Load Balancing. Auxiliary losses (Lepikhin et al., 2021; Fedus et al., 2022) and capacity clipping (Lepikhin et al., 2021) are heuristics to approximate it.

### Expert Choice: Relaxing Sparsity

EC (Zhou et al., 2022) takes a fundamentally different approach: instead of enforcing sparsity (fixed experts per token), EC removes the sparsity constraint entirely and enforces only load balancing. Each expert independently selects its top-$k$ tokens with highest routing scores:

$$
\begin{aligned}
\max_{\mathbf{z}} \quad & \sum_{i=1}^{G_E} \left( \sum_{t=1}^{N} z_{t,i} r_{t,i} \right) \\
\text{s.t.} \quad & \sum_{t=1}^{N} z_{t,i} = k, \quad \forall i \\
& z_{t,i} \in \{0, 1\}
\end{aligned}
\tag{2}
$$

with closed-form solution $z_{t,i} = \mathbb{1}\{t \in \text{Top}_k(\mathbf{r}_{\cdot,i})\}$. This design has two key consequences:
1. **Perfect load balancing**: each expert processes exactly $k = N/E$ tokens by construction, eliminating the need for auxiliary losses or capacity clipping;
2. **Dynamic computation**: a token may be selected by zero, one, or multiple experts, enabling adaptive compute allocation based on token importance.

However, EC introduces a causality problem for autoregressive generation. The selection indicator $z_{t,i}$ depends on all tokens' scores $\{r_{1,i}, \dots, r_{N,i}\}$—including future tokens unavailable during inference. Extending EC to batch-level top-$k$ (Ludziejewski et al., 2024) partially alleviates this but does not fully restore causality, as routing still depends on batch composition.

### ET: Stochastic Relaxation

ET further relaxes the per-batch Load Balancing constraint to a stochastic expectation:

$$
\begin{aligned}
\max_{\mathbf{z}} \quad & \mathbb{E}_{\text{data}} \left[ \sum_{i=1}^{G_E} z_{t,i} r_{t,i} \right] \\
\text{s.t.} \quad & \mathbb{E}_{\text{data}}[z_{t,i}] = \frac{1}{E}, \quad \forall i \\
& z_{t,i} \in \{0, 1\}
\end{aligned}
\tag{3}
$$

This replaces batch-dependent ranking with population-level thresholding:

$$
z_{t,i} = \mathbb{1}\{r_{t,i} > c_i\}
\tag{4}
$$

where $c_i$ is the $(1 - 1/E)$-quantile of expert $i$'s score distribution, estimated via EMA from historical batches. Since $z_{t,i}$ depends only on $r_{t,i}$ and the global threshold $c_i$, routing is fully causal while satisfying load balancing in expectation.

---

## 3. Methods

Suppose we have an expansion rate of $E$ (i.e., the sparsity ratio). For each expert, ET seeks to pick the top $1/E$ fraction of tokens from the full router logit distribution, rather than from a single batch. To do so, let $N$ be the number of tokens in a batch and $k = N/E$ be the ideal number of selected tokens in a batch under perfect load balance for each expert.

ET records the exponential moving average (EMA) of the cutoff threshold, i.e. the value of the $k$-th largest router logit of each batch. Conceptually, this cutoff-EMA $c_i$ serves as a statistical estimator of the $1/E$-quantile of the router logit distribution. Then, for both training and inference, we route tokens via binary thresholding, setting $z_{t,i} = \mathbb{1}\{r_{t,i} > c_i\}$ where $z_{t,i} \in \{0,1\}$ is the binary indicator of whether token $t$ is routed to expert $i$.

Population-level thresholding decouples routing decisions from batch composition. Essentially, we no longer fix the number of activated tokens in a batch, but only seek to do so asymptotically. In exchange, we smooth the batch-to-batch fluctuations of the cutoff threshold, yielding more consistent routing during training. The larger effective decision pool creates greater potential for expert specialization (Qiu et al., 2025). Meanwhile, routing at inference becomes fully causal as we only need the global statistics of the cutoff-EMA and not any information about the current batch. Thus, we eliminate the train-inference mismatch of EC.

### Warmup

At the beginning of training, the router logits' distribution is not stable yet. The cutoff-EMA requires several thousand steps to converge to a meaningful estimate of the population quantile. During this period, incorrect thresholds cause severe expert starvation—most tokens fail to exceed the threshold, leaving experts underutilized. To address this cold-start problem, we use standard EC routing for the first 4k steps before switching to ET. This allows the cutoff-EMA to accumulate stable statistics under controlled load balance.

### Expert Capacity

With ET, the number of tokens activating each expert is no longer fixed but fluctuates slightly around the target capacity. To avoid GPU out-of-memory, we enforce expert capacity during training time to bound the number of tokens activating each expert (Fedus et al., 2022). This design introduces a small discrepancy between training and inference time, which we find acceptable.

### Shared Expert

Unlike Token-choice MoE which always activates some experts, Expert Choice models may have zero experts selected for certain tokens, which we hypothesize to cause issues with later layers' routing. To address this, we add a shared expert $M_0$ (Dai et al., 2024; Komatsuzaki et al., 2023) that processes every token, ensuring non-trivial expert output even when no routed experts are activated.

### Gating

Following LossFree (Wang et al., 2024) and Mixture-of-Depths (Raposo et al., 2024), we use sigmoid gates ($p_{t,i} = \sigma(r_{t,i})$) instead of softmax gates.

### Algorithm 1: Expert Threshold Routing

```
Input: router logits r ∈ ℝ^(N×G_E), cutoff-EMA {c_i}, 
       decay rate β, target selection size k = N/E

for expert i = 1, ..., G_E do
    z_{t,i} ← 𝟙{r_{t,i} > c_i} ∀t
    if TRAINING then
        c_i ← β·c_i + (1-β) · kth-largest({r_{t,i}}_{t=1}^N, k)
    end if
end for

Return z, {c_i}
```

---

## 4. Experiments

### 4.1. Experiment Setup

We evaluate our methods on Nanochat (Karpathy, 2025), an open-source codebase for training GPT-2-like models. We conduct experiments at two scales:
- **d12 model**: 575M parameters, 195M active, with 12 transformer layers
- **d20 model**: 2.4B parameters, 561M active, with 20 transformer layers

For MoE layers, we use 16 routed experts ($G=2$, $E=8$) plus 1 shared expert; each token activates the shared expert and on average 1 routed expert. The first layer is kept dense following common practice (DeepSeek-AI, 2024; Wang et al., 2024) to allow meaningful routing. We train on 10B and 11.2B tokens for d12 and d20, respectively, from the FineWeb-Edu 100B dataset (Penedo et al., 2024) with a batch size of 0.5M tokens (for d20, we halve the minibatch size and use 2-step gradient accumulation).

We report CE loss and CORE benchmark results (Li et al., 2024). Architecture, training, and evaluation details are in Appendices B, C, and D.

### 4.2. Main Results

We compare Expert Threshold (ET) against Expert Choice (EC) and Token Choice (TC) routing. All variants share the same architecture and parameter count. For ET, we use EMA decay $\beta = 0.999$ and capacity $C = 0.5$; we also evaluate a variant with EC warmup for the first 4k steps. For EC, we sweep the global selection batch size from 2k to 512k tokens. For TC, we report variants with no load balancing, auxiliary loss ($\alpha=0.001$), and loss-free load balancing ($\mu=0.005$).

**Table 1: Main results comparing EC, TC, and ET routing**

| Method | Batch | CE loss (↓) | CORE (↑) |
|--------|-------|-------------|----------|
| TC — | — | 2.893 | 17.983 |
| TC aux | 64k | 2.892 | 15.894 |
| TC loss-free | 512k | 2.898 | 18.031 |
| EC | 2k | 2.910 | 17.91 |
| EC | 8k | 2.845 | 18.83 |
| EC | 64k | 2.841 | 18.754 |
| EC | 512k | 2.843 | 19.94 |
| ET ($\beta$=0.999) | ~500M | 2.844 | 16.867 |
| ET ($\beta$=0.999+warmup) | 0.5M→500M | 2.844 | **19.876** |

**Table 2: d20 results**

| Method | Batch | CE loss (↓) | CORE (↑) |
|--------|-------|-------------|----------|
| dense | — | 2.751 | 20.43 |
| TC aux | 32k | 2.687 | 22.31 |
| EC | 256k | 2.621 | 24.98 |
| ET ($\beta$=0.999+warmup) | 256k→500M | **2.620** | **25.14** |

**Key findings:**
- ET+warmup consistently outperforms TC in both CE loss (by 0.05 on d12 and 0.067 on d20) and CORE (by 1.89 on d12 and 2.83 on d20)
- EC with large batch sizes achieves comparable CE loss to ET, confirming that explicit large-batch selection and EMA-based thresholding reach similar training loss
- EC 512k slightly edges out ET+warmup on CORE (19.94 vs. 19.88) in d12, though both substantially outperform TC
- Critically, ET without warmup suffers degraded downstream performance (CORE 16.87, below even baseline TC at 17.98) despite matching ET+warmup in CE loss

### 4.3. Analysis

#### 4.3.1. BATCH SIZE SCALING

We examine how EC's routing batch size affects model quality. Table 1 shows EC across four batch sizes (2k, 8k, 64k, 512k tokens). Larger batches yield better performance: training CE loss improves from 2.874 (2k) to 2.855 (8k) to 2.836 (64k), with CORE Eval scores following a similar trend (17.91 → 18.76 → 19.62). This is expected: top-$k$ selection over larger token pools better approximates the population-level routing decision. However, performance saturates around 64k tokens—increasing to 512k provides no further gain (2.843 CE, 19.94 CORE Eval).

> **Figure 2 description**: A dual-axis plot showing EC performance across routing batch sizes (2k, 8k, 64k, 512k, and ET). Left y-axis shows Train CE Loss (decreasing trend), right y-axis shows CORE % (increasing trend). Both metrics improve with larger batches but plateau beyond 64k tokens. ET achieves comparable performance without batch size constraints.

#### 4.3.2. TRAIN-EVALUATION GAP

A key concern for Expert Choice is the discrepancy between training and inference. During training, EC selects the top-$k$ tokens for each expert within a batch; during autoregressive inference, future tokens are unavailable, making batch-level top-$k$ selection impossible. Prior work addresses this via auxiliary predictors (Raposo et al., 2024) or batch-level approximations (Ludziejewski et al., 2024), but these introduce additional complexity or latency.

Our results demonstrate that this concern depends critically on the routing batch size. As shown in Table 1, EC with large batch sizes (64k, 512k) achieves validation loss nearly identical to ET (2.841–2.843 vs 2.844), with comparable CORE Eval scores. However, smaller batch sizes reveal significant train-inference mismatch: EC at 2k tokens shows degraded CORE Eval performance (17.91 vs 19.94 at 512k) and evaluation loss (2.910 vs 2.843). This gap arises because top-$k$ selection over a small batch is a noisy estimate of the population-level routing decision; at inference (batch size 1), this noise becomes extreme.

> **Figure 3 description**: Plot of train-eval gap (eval loss − train loss EMA) for EC at different batch sizes over training steps. EC(2k) shows a large gap that spikes during training; EC(512k) remains near zero, demonstrating EC's sensitivity to routing batch size.

#### 4.3.3. CUTOFF VS EXPERT USAGE TRADEOFF

EC and ET achieve routing stability through complementary mechanisms:
- **EC**: Enforces fixed expert usage (each expert selects exactly top-$k$ tokens, guaranteeing usage of $1/E$ per expert). However, the cutoff threshold varies batch-to-batch, with standard deviation scaling as $O(1/\sqrt{N})$.
- **ET**: The cutoff-EMA provides a stable threshold ($\beta=0.999$), while expert usage fluctuates around the capacity target.

> **Figure 4 description**: Two-panel plot showing the cutoff stability vs expert usage tradeoff.
> - Top panel: Cutoff Absolute Deviation from EMA. EC(512k) shows non-zero deviation; ET achieves zero deviation by design.
> - Bottom panel: Expert Usage. EC usage is fixed at 1/16 by top-$k$ selection; ET usage varies around the capacity target.

#### 4.3.4. DYNAMIC COMPUTATION ALLOCATION

A key advantage of ET/EC is its ability to dynamically allocate computation to different tokens.

> **Figure 5(a) description**: Per-token expert routing visualization on a GSM8K passage. Tokens are colored by total fanout (sum of experts activated across layers). The model allocates more computation to structurally important tokens—such as punctuation, sentence boundaries, and numerical results—while assigning fewer experts to common content words. This adaptive allocation suggests that EC/ET learns to concentrate capacity on tokens requiring more complex reasoning.

#### 4.3.5. EXPERT SPECIALIZATION

We follow Global LBL (Qiu et al., 2025) to evaluate expert specialization across EC with various batch sizes (2k, 8k, 64k, 512k) and ET. For each configuration, we measure the expert token ratio—the fraction of tokens from a given domain routed to each expert—across HumanEval (code) and GSM8K (math) evaluation sets.

> **Figure 5(b) description**: Expert activation heatmaps comparing EC (batch size 2k) with ET (warmup). Each heatmap plots Expert ID (columns) vs Layer (rows), with color intensity indicating expert token ratio for HumanEval (code) and GSM8K (math) domains.
> - Top (EC 2k): Shows less specialization with diffuse activation patterns
> - Bottom (ET warmup): Shows more extreme activation patterns with concentrated dark cells, suggesting more domain-aware routing and sharper specialization comparable to large-batch EC

### 4.4. Comparison to Token Choice

> **Figure 6 description**: Plot of Layer-1 cutoff-EMA (expert 0) under EC/ET vs DeepSeek loss-free load balancing over training steps. EC/ET quickly stabilizes, while DeepSeek's loss-free controller drifts upward, indicating persistent imbalance. This is consistent with reports that loss-free load balancing becomes unstable when load statistics are noisy (Wang et al., 2024).

EC/ET achieves more stable load balancing than Token Choice, especially in early layers. We conjecture that once routing concentrates, bias updates lose their corrective signal.

### 4.5. Ablations

#### Warmup

We find warmup crucial for ET. In the early stages of training, the cutoff threshold is not yet stable, while the EMA lags behind the actual cutoff threshold because of slow update speed ($1/(1-\beta) \approx 1000$ steps). As a result, threshold-based routing becomes unreliable: tokens that should be routed are dropped, and the capacity lower bound is frequently triggered. This leads to undertrained experts during early training.

To address this, we warm up the routing by using TopK selection for the first 4,000 steps before switching to threshold-based routing.

> **Figure 7 description**: Six-panel plot showing effect of TopK warmup on ET training dynamics (first 8k steps).
> - (a) L9 cutoff vs EMA: ET without warmup shows cutoff-EMA lagging behind actual cutoff; warmup stabilizes trajectory
> - (b) Raw expert usage: Higher with warmup
> - (c) Starvation rate: Lower with warmup (capacity lower bound triggered less frequently)
> - (d) L6 cutoff-EMA: More stable with warmup
> - (e) Router logits std: Lower variance with warmup
> - (f) Gate std: Lower variance with warmup

#### Shared Expert

**Table 3: Ablation on the shared expert mechanism**

| Method | Shared | CE | CORE |
|--------|--------|-----|------|
| EC (bsz 512k) | Yes | 2.843 | 19.94 |
| EC (bsz 512k) | No | 2.862 | 16.307 |
| ET ($\beta$=0.999) | Yes | 2.844 | 16.867 |
| ET ($\beta$=0.999) | No | 2.862 | 18.515 |

In both ET and EC, shared expert improves loss by roughly 0.02. We suspect that while later layers need early layers to empower the router, sometimes early layers have no activated experts, causing ineffective routing.

---

## 5. Related Work

### 5.1. Mixture of Experts

Mixture of Experts (MoE) scales model capacity by routing each token to a small subset of experts while keeping compute nearly constant. A learned gate selects top-$G$ experts per token (Shazeer et al., 2017), with auxiliary losses to balance load across experts (Lepikhin et al., 2021). The Switch Transformer (Fedus et al., 2022) sets $G=1$ for efficiency. Recent LLMs further adopt fine-grained MoE with many small experts and shared experts that remain always active to capture global knowledge (Dai et al., 2024). We incorporate shared experts in our design.

### 5.2. Load Balancing

A critical challenge in MoE systems is load balancing: without explicit constraints, routers often favor a small subset of experts, leading to expert collapse. The standard approach uses an auxiliary loss $\mathcal{L}_{\text{aux}}$ to encourage uniform expert assignment (Lepikhin et al., 2021; Fedus et al., 2022).

For a batch of $N$ tokens and $G_E$ experts, we define the normalized load $f_i$ and average routing probability $P_i$ for expert $i$:

$$
f_i = \frac{E}{N} \sum_{t=1}^{N} z_{t,i}, \quad P_i = \frac{1}{N} \sum_{t=1}^{N} p_{t,i}
$$

where $z_{t,i} \in \{0,1\}$ is the indicator that expert $i$ is selected for token $t$, $p_{t,i}$ is the routing probability, and $E$ is the expansion factor. Under Top-$G$ routing, $f_i = 1$ implies perfect load balancing. The auxiliary loss is:

$$
\mathcal{L}_{\text{aux}} = \alpha \sum_{i=1}^{G_E} f_i P_i
$$

where $\alpha$ is a coefficient (typically $10^{-2}$ to $10^{-4}$). However, in distributed training, the small local batch size $N$ causes high variance in load estimation. Global-batch load balancing (Qiu et al., 2025; Team, 2025b) addresses this by computing balance statistics across all devices.

**Table 4: Taxonomy of load balancing methods by scope**

| Scope | Micro | Batch/Seq | Batch | Population |
|-------|-------|-----------|-------|------------|
| Aux loss | ✓ | – | – | – |
| Global LBL | – | ✓ | – | – |
| LossFree | – | – | ✓ | – |
| Seq EC | – | ✓ | – | – |
| Batch EC | – | – | ✓ | – |
| **ET (ours)** | – | – | – | ✓ |

**Table 5: Conceptual connections between ET and recent work**

| ET Component | Similar To | Connection |
|--------------|------------|------------|
| Cutoff-EMA $c_i$ | LossFree bias $b_i$ | Per-expert scalar; no aux loss |
| $1-\beta$ | LossFree $\mu$ | Update rate |

Recent work explores auxiliary-loss-free alternatives:
- **DeepSeekMoE** (Dai et al., 2024): Introduces expert-specific bias terms $b_i$ that dynamically adjust based on load statistics
- **LongCat-Flash** (Team, 2025a): Replaces sign-based update with proportional control: $\Delta b_i = \mu \cdot (1 - f_i)$

Expert Threshold (ET) combines these ideas by extending the philosophy to compute balance statistics across the entire pretrain population via EMA-based global cutoff thresholds.

### 5.3. Dynamic Computation

Dynamic computation methods adaptively allocate computational resources based on input complexity. Expert Choice (EC) (Zhou et al., 2022) achieves this by letting each expert select its top-$k$ tokens, enabling variable computation per token (0 to $G_E$ experts). EC has been applied to upcycling dense checkpoints, attention layer skipping, vision, diffusion, and multimodal models.

Other approaches to dynamic computation include:
- **ReMoE** (Wang et al., 2025b): Replaces discrete Top-$G$ routing with fully differentiable ReLU-based routing
- **Zero-computation experts** (Jin et al., 2024; Team, 2025a; Zeng et al., 2024): Allow tokens to skip expert computation entirely
- **Top-P routing** (Liu et al., 2025b; Jin et al., 2025): Selects experts based on cumulative probability mass
- **Threshold-based routing** (e.g., XMoE (Yang et al., 2024)) and auto-tuning methods like DynMoE (Guo et al., 2025)

### 5.4. Causal Generation of Expert Choice Models

EC poses a causality challenge: token selection requires ranking against future tokens, which are unavailable in autoregressive generation. Prior work addresses this via:
1. **Predictor-based methods**: Train auxiliary predictors to approximate oracle top-$k$ decisions
2. **Batch-level top-$k$**: Selection across current tokens from different sequences
3. **Segment-level routing**: Lory routes at segment level using previous segment to determine next
4. **Sequence-level selection**: SeqTopK shifts expert budgets to sequence-level with Expert Cache

All above approaches have significant drawbacks: predictions can be noisy, batch-level top-$k$ imposes inference-time constraints, and routing dependent on global batch composition raises privacy/safety concerns. In contrast, ET reduces to a simple threshold test ($r_{t,i} > c_i$) at inference, eliminating train-inference discrepancy.

### 5.5. From Batch to Population Level Statistics

The progression from sample, batch, to population-level statistics is a recurring theme in deep learning. While techniques like Batch Normalization and contrastive learning rely on batch statistics, momentum-based approaches and adaptive optimizers like Adam use Exponential Moving Averages (EMA) to approximate population distributions. ET applies this principle to routing via EMA-based cutoffs.

---

## 6. Conclusion

We introduce **Expert Threshold (ET)**, a routing mechanism that resolves the fundamental causality issue in Expert Choice (EC) models while preserving their load-balancing advantages. By maintaining an exponential moving average of each expert's selection threshold—estimated from historical batches rather than within-batch top-$k$ selection—ET enables fully causal routing: each token's routing decision depends only on past statistics, eliminating the need for future token access at both training and inference time.

Our experiments demonstrate that ET achieves competitive performance with EC (matching validation loss at 2.84) while outperforming Token Choice by 0.067 in cross-entropy loss, all while enabling causal autoregressive generation. The cutoff-EMA mechanism provides stable routing thresholds that accurately approximate EC's top-$k$ boundaries, as evidenced by the minimal train-inference gap observed across all metrics. We further show that a warmup strategy—using EC's top-$k$ routing before transitioning to threshold-based selection—stabilizes early training dynamics.

These findings suggest that the perceived incompatibility between Expert Choice routing and causal language modeling can be effectively bridged through population-level threshold estimation, opening new directions for scalable MoE architectures.

---

## Acknowledgments

We gratefully acknowledge the support of NVIDIA Corporation and the NVIDIA AI Technology Center (NVAITC) UF program.

## Impact Statement

This paper presents work whose goal is to advance the field of Machine Learning. There are many potential societal consequences of our work, none which we feel must be specifically highlighted here.

---

## References

*(Selected key references; full list available in original paper)*

- Ainslie, J., et al. GQA: Training generalized multi-query transformer models from multi-head checkpoints, 2023a.
- Chi, Z., et al. On the representation collapse of sparse mixture of experts. *NeurIPS*, 2022.
- Dai, D., et al. DeepSeekMoE: Towards ultimate expert specialization in mixture-of-experts language models, 2024.
- Fedus, W., Zoph, B., & Shazeer, N. Switch transformers: Scaling to trillion parameter models with simple and efficient sparsity. *JMLR*, 2022.
- Lepikhin, D., et al. GShard: Scaling giant models with conditional computation and automatic sharding. *ICLR*, 2021.
- Ludziejewski, J., et al. Scaling laws for fine-grained mixture of experts. *ICML*, 2024.
- Penedo, G., et al. The FineWeb datasets: Decanting the web for the finest text data at scale. *NeurIPS Datasets*, 2024.
- Qiu, Z., et al. Demons in the detail: On implementing load balancing loss for training specialized mixture-of-expert models, 2025.
- Wang, L., et al. Auxiliary-loss-free load balancing strategy for mixture-of-experts, 2024.
- Zhou, Y., et al. Mixture-of-experts with expert choice routing. *NeurIPS*, 2022.

---

## Appendices

### A. Future Information Leakage for Expert Choice Models

*(Technical appendix analyzing information-theoretic bounds on EC's causality violation; shows ET with finite-precision cutoffs maintains causality)*

### B. Architecture Details

**Table 6: Model architecture and size configurations**

| Feature | GPT-2 | d12 | d20 |
|---------|-------|-----|-----|
| Tokenization | GPT-2 | RustBPE | RustBPE |
| Vocab Size | 50,257 | 65,536 | 65,536 |
| Activation | GELU | ReLU² | ReLU² |
| Normalization | LayerNorm | RMSNorm | RMSNorm |
| FFN Dimension | 4×d_model | 4×d_model | 4×d_model |
| Position Encoding | Learned | RoPE | RoPE |
| Head Dimension | 64 | 128 | 128 |
| QK Normalization | No | Yes | Yes |
| Logits Softcapping | No | 15.0 | 15.0 |
| Embedding Weights | Tied | Untied | Untied |
| First Layer Dense | — | Yes | Yes |
| n_embd | 768 | 768 | 1280 |
| n_layer | 12 | 12 | 20 |
| n_head | 12 | 6 | 10 |
| KV heads | 12 | 2 | 2 |
| Dense Params | 124M | 195M | 561M |
| MoE Total Params | — | 575M | 2.43B |
| MoE Active Params | — | 195M | 561M |

### C. Training Setup Details

**Table 7: Training hyperparameters**

| Hyperparameter | Value |
|---------------|-------|
| Total tokens | 10B / 11.2B |
| Batch size (tokens) | 524,288 (0.5M) |
| Sequence length | 2048 |
| Muon Warmup steps | No warmup |
| AdamW Warmup steps | 250 |
| Learning rate schedule | Linear decay |
| Min learning rate | 0.1× peak LR |
| Gradient clipping | None |
| Weight decay | 0.0 |
| AdamW $\beta_1, \beta_2$ | 0.9, 0.95 |

### D. CORE Evaluation Details

- **Task types**: Multiple-choice, schema matching, language modeling
- **Metric**: Centered accuracy: $\text{acc}_{\text{centered}} = \frac{\text{acc} - 0.01 \times \text{baseline}_{\text{random}}}{1.0 - 0.01 \times \text{baseline}_{\text{random}}}$
- **Protocol**: Evaluation at fixed intervals during training (every 250 steps)

### E. Additional Experiment Results

> **Figure 9 description**: Capacity constraint behavior during ET training (from step 4k onward, after warmup).
> - (a) Raw Expert Usage: Stabilizes around 6.5%
> - (b) Saturation Rate: Fraction of selected tokens dropped due to capacity limits; remains low
> - (c) Starvation Rate: Fraction of unused expert capacity; remains low
> Both saturation and starvation rates remain low, confirming minimal train-inference mismatch.

> **Figures 10-12 descriptions**: Per-layer expert fanout and full routing visualizations on GSM8K and HumanEval passages. Numerical and code-specific tokens receive substantially higher fanout than function words. Routing patterns reveal domain-specific structure.

> **Figure 13 description**: Expert activation heatmaps across routing configurations (EC with batch sizes 2k, 8k, 64k, 512k, and ET with warmup). Specialization sharpens with larger EC batch sizes; ET warmup achieves comparable patterns without batch size dependence.

> **Figure 14 description**: Comparison of evaluation loss with and without normalization. The configuration without normalization consistently achieves lower loss than the fanout-normalized variant.

### F. Failed Attempts

#### F.1. Normalization

Initially, we assumed that dynamic expert count would bring instability in training because of scale expansion. However, we found that normalization is proven to be ineffective. No norm outperformed fanout norm by 0.04 in CE loss. We suspect that the norm made experts' contribution unpredictable.