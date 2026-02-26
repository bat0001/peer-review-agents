# Notation (`example_paper.tex`)

This is a notation glossary for symbols appearing in `example_paper.tex`.

## Typography & conventions

- Scalars: italic Latin/Greek (e.g., $N,d,k,\alpha,\beta,\mu,\tau,\lambda,\sigma$).
- Vectors: lowercase with subscript (e.g., $x_t \in \mathbb{R}^d$).
- Matrices/tensors: uppercase (e.g., $X, W, G$) with explicit shapes when provided.
- Sets/collections/modules: calligraphic ($\mathcal{M}_i,\mathcal{L}$).
- Number spaces: blackboard bold ($\mathbb{R}$); indicators ($\mathbb{1}\{\cdot\}$); bold constants ($\mathbf{0}$).
- Text metrics/flags: monospace (e.g., `norm_selected_ratio`, `select_norm`).

## Indices

| Index | Meaning |
|---|---|
| $t$ | token index in the routing pool, $t \in \{1,\dots,N\}$ |
| $i$ | routed expert index ($i \in \{1,\dots,GE\}$) |
| $j$ | expert index (only in the mapping tables / common notation) |
| $l$ | transformer layer index (MoD/early-exit related work) |

## Core method (GEC with shared expert)

### Dimensions / counts

| Symbol | Meaning | Type/Shape |
|---|---|---|
| $N$ | number of tokens in the routing pool (often written as $BT$ when flattening a batch) | scalar |
| $d$ | embedding / residual dimension | scalar |
| $E$ | expansion rate (total params / active params) | scalar |
| $G$ | granularity (expert FFN dim / dense FFN dim) | scalar |
| $GE$ | number of routed experts | scalar |
| $k$ | per-expert selection size, $k=\lfloor N/E \rfloor$ | scalar |

### Router / gating / thresholds

| Symbol | Meaning | Type/Shape |
|---|---|---|
| $W_r$ | router weight matrix (if parameterizing $r_t = W_r x_t$) | matrix |
| $r_{t,i}$ | router logit for token $t$ and expert $i$ | scalar |
| $r_t$ | vector of router logits for token $t$ | $\in \mathbb{R}^{GE}$ |
| $\sigma(\cdot)$ | sigmoid used for gating, $\sigma(x)=1/(1+e^{-x})$ | function |
| $p_{t,i}$ | gate value (sigmoid/softmax/etc.), $p_{t,i}=\sigma(r_{t,i})$ for sigmoid | scalar |
| $c_i$ | learned cutoff/threshold for expert $i$ (tracked by EMA) | scalar |
| $\beta$ | EMA decay for $c_i$ updates | scalar in $(0,1]$ |

### Experts / dispatch sets / outputs

| Symbol | Meaning | Type/Shape |
|---|---|---|
| $\mathcal{M}_0$ | shared expert (always active) | module |
| $\mathcal{M}_i$ | routed expert $i$ | module |
| $x_t$ | token embedding/residual input | $\in \mathbb{R}^d$ |
| $z_{t,i}$ | binary dispatch indicator (expert $i$ processes token $t$) | $\in \{0,1\}$ |
| $y_{0,t}$ | shared expert output for token $t$ | $\in \mathbb{R}^d$ |
| $y_{i,t}$ | routed expert output for token $t$ | $\in \mathbb{R}^d$ |
| $y_t$ | aggregated output $y_t = y_{0,t} + \sum_{i=1}^{GE} z_{t,i}\,p_{t,i}\,y_{i,t}$ | $\in \mathbb{R}^d$ |

### Tensors

| Symbol | Meaning | Type/Shape |
|---|---|---|
| $X$ | batch tensor | $\in \mathbb{R}^{B\times T\times d}$ |
| $X_{\text{flat}}$ | flattened token batch | $\in \mathbb{R}^{(BT)\times d}$ |
| $R_{\text{logits}}$ | router logits for all tokens/experts | $\in \mathbb{R}^{(BT)\times GE}$ |

## Background / related work notation appearing in the text

### Expert Choice (EC) description

| Symbol | Meaning | Type/Shape |
|---|---|---|
| $r$ | routing logit matrix | $\in \mathbb{R}^{N\times GE}$ |
| $N$ | number of tokens being ranked (EC discussion) | scalar |
| $GE$ | number of experts (EC discussion) | scalar |
| $r_{t,i}$ | score/logit for token $t$ and expert $i$ | scalar |
| $L$ | (Upper bound) maximum future information leakage in bits per token for Expert Choice routing allocations (loss-free load balancing discussion) | scalar |

### Mixture of Depths (MoD) / other dynamics

| Symbol | Meaning | Notes |
|---|---|---|
| $l$ | layer index | |
| $r_i^l$ | router score for token $i$ at layer $l$ | defined as $W_r^T x_i^l$ |
| $x_i^l$ | token representation at layer $l$ | |
| $\mathcal{L}_{\text{aux}}$ | auxiliary BCE loss for routing | (MoD discussion; same symbol reused later) |
| $y_i$ | binary label for whether token is selected | (MoD discussion) |

### Load balancing / routing stats

| Symbol | Meaning |
|---|---|
| $\mathcal{L}_{\text{aux}}$ | auxiliary load-balancing loss |
| $\alpha$ | coefficient for $\mathcal{L}_{\text{aux}}$ |
| $GE$ | number of experts (load-balancing section) |
| $N$ | total number of tokens in a batch |
| $p(x)$ | routing probability vector for token $x$ |
| $p_i(x)$ | $i$-th routing probability component |
| $f_i$ | normalized load for expert $i$ (for our configs with $GE=G\,E$), $f_i=\frac{E}{N}\sum_{t=1}^N z_{t,i}$ |
| $f^*$ | target load for expert $i$, $f^*=1$ |
| $P_i$ | normalized probability mass, $P_i=\frac{1}{N}\sum_{t=1}^N p_{t,i}$ |
| $\Delta b_i$ | bias update (PID load balancing discussion) |
| $b_i$ | per-expert bias term (related work) |
| $\mu$ | step size in PID-style update |
| $u$ | bias update step size in DeepSeek discussion |

## Training / initialization / optimizer notation

| Symbol | Meaning | Notes |
|---|---|---|
| $\beta_1, \beta_2$ | AdamW momentum coefficients | |
| std | standard deviation used in weight initialization | |
| $r_p$ | ratio total params / active params (used in init scaling) | |
| $W$ | generic weight matrix | $W\in\mathbb{R}^{d_{\text{out}}\times d_{\text{in}}}$ |
| $d_{\text{in}}, d_{\text{out}}$ | input/output dimensions for $W$ | |
| $\lambda$ | $\mu$P learning-rate scaling factor | $\lambda=(d_{\text{model}}/768)^{-1/2}$ |
| $W_E, W_{\text{lm}}, W_{QKV}, W_O$ | embedding / head / attention parameter blocks | |
| $W_{\text{router}}$ | router parameter block | |
| $W^{(e)}_{\uparrow}, W^{(e)}_{\downarrow}$ | expert up/down projection weights | |
| $W^{(s)}_{\uparrow}, W^{(s)}_{\downarrow}$ | shared up/down projection weights | |
| $\mathbf{0}$ | zero initialization | |

## Disambiguation

- We use $r$ for router logits throughout; avoid introducing extra symbols for the same quantity.
- We use $p$ for gate values (sigmoid/softmax/etc.). Here $p_{t,i}$ is a per-token/per-expert gate value (not necessarily normalized across experts), while $p_i(x)$ denotes the $i$-th component of a token-choice MoE routing distribution.
- $G$ is overloaded: it denotes granularity in the core method, and top-$G$ denotes the number of experts selected per token in token-choice routing.

## Related-work notation mapping (original $\rightarrow$ this paper)

This section documents how we rewrite symbols from cited work into the unified notation used in `example_paper.tex`.

### Expert Choice (EC)

| Common EC notation | This paper | Meaning |
|---|---|---|
| $S$ | $N$ | number of tokens being ranked |
| $G \in \mathbb{R}^{S\times E}$ | $r \in \mathbb{R}^{N\times GE}$ | routing scores / logits |
| $E$ | $GE$ | number of experts |
| $G_{t,j}$ | $r_{t,i}$ | token--expert score |

### Mixture of Depths (MoD)

| MoD notation | This paper | Meaning |
|---|---|---|
| $\beta$ | $1/E$ | fraction of tokens processed (top $N/E$ tokens) |
| $w_\theta$ | $W_r$ | router weights |

### DeepSeekMoE load-stat updates

| DeepSeek notation | This paper | Meaning |
|---|---|---|
| $s_{i,t}$ | $r_{t,i}$ | (pre-bias) routing score used for selection/weights |
| $c_i,\;\bar c_i$ | $f_i$ (target $=1$) | expert load (normalized so perfect balance is 1) |
| $\text{sign}(\bar c_i-c_i)$ | $\text{sign}(1-f_i)$ | bias update direction |

### Aux-load-balancing loss (GShard/Switch style)

| Standard form | This paper | Notes |
|---|---|---|
| $\alpha\,GE\sum_i f_i P_i$ with $\sum_i f_i=\sum_i P_i=1$ | $\frac{\alpha}{GE}\sum_i f_i P_i$ with $f_i,P_i\approx 1$ when balanced | same idea; different normalization convention |
