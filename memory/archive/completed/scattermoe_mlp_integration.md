# Plan: ScatterMoE-kernel-backed **token-choice** MoE MLP (`src/models/`)

This plan is updated to match current decisions:
- **Reuse only ScatterMoE kernels** (Triton code) from `scattermoe/scattermoe/kernels/ops.py`.
- **Write our own PyTorch/autograd wrapper** in repo style (do not instantiate ScatterMoE `MLP`/`ParallelExperts`).
- **Packed 2D expert parameters** (DDP-friendly; works with `DistMuon`).
- **Router activation uses the same utility as GEC**: `src/models/router_utils.apply_router_activation` (no custom activation code).
- Baseline research can default to `router_activation: sigmoid`.
- Support both **aux-loss** load balancing *and* **DeepSeek-style loss-free bias updates**.

---

## Goal

Add a new `BaseMLP` implementation (token-choice MoE: top-k experts per token) that:
1) routes tokens → experts (top_k per token, derived from granularity/expansion),
2) runs the expert MLP using ScatterMoE’s fused Triton path (`scatter2scatter`, `group`, `group_bwd_W`),
3) supports both:
   - **aux-loss** (Switch/GShard style), and
   - **loss-free** DeepSeek bias update,
4) integrates cleanly with the repo’s:
   - meta → `to_empty()` → `init_weights()` init rules,
   - DDP optimizer grouping (`DistMuon` 2D-only),
   - metrics plumbing (tensor metrics inside model, Python scalars in train loop).

Primary motivation: a performant **token-choice MoE baseline** using proven Triton kernels while keeping our codebase consistent.

---

## Non-goals (initially)

- Editing anything in `scattermoe/` (vendored reference).
- EP (expert-parallel) for this MoE (ScatterMoE kernels are single-device; we run multi-GPU via DP/DDP).
- New Triton kernels in this repo.
- Expert-choice routing (GEC/EC) using ScatterMoE kernels (they assume fixed `top_k` fanout per token).

---

## Key repo constraints (must respect)

### 1) Meta init + naming-based init rules

The model is created under `torch.device("meta")`, then `to_empty()`, then `BaseGPT.init_weights()`.
`init_weights()` uses **parameter name heuristics** (e.g. anything containing `weight2` is zero-init).

Implication: the new module must use the canonical names:
- `router.weight` (small init)
- `expert_weight1` (normal init)
- `expert_weight2` (zero init, because name contains `weight2`)

### 2) DDP optimizer (`DistMuon`) is 2D-only

`DistMuon` asserts `all(p.ndim == 2)`.

Implication: expert weights must be packed 2D parameters and `view()`’d to 3D for kernels at runtime.

---

## What we reuse from ScatterMoE (kernel surface only)

We reuse only the kernel ops:
- `scattermoe/scattermoe/kernels/ops.py`
  - `scatter2scatter(...)` (Triton)
  - `group(...)` (Triton)
  - `group_bwd_W(...)` (Triton)

We do **not** instantiate ScatterMoE’s:
- `scattermoe/scattermoe/mlp.py` (`MLP`, `GLUMLP`)
- `scattermoe/scattermoe/parallel_experts.py` (`ParallelExperts`, `ParallelLinear`)

We *can* mirror their wrapper logic, but we keep it in our repo and in our naming/init conventions.

---

## Model/Config surface (proposed)

### New model type

Add a new `model_type` string, e.g.:
- `scattermoe_tc` (explicit: token-choice)

Call sites to update:
- `src/models/model_base.py` (`ModelConfig.__post_init__` allowlist + `BaseGPT._get_mlp_class`)
- `src/config.py` (`Config.validate()` allowlist)
- `src/models/README.md` (document new model type)
- `configs/mlp/` (new Hydra group)

### New config fields

Add to `ModelConfig`:
- `load_balance_method: str = "none"`  # `"none" | "aux" | "deepseek"`
- `aux_loss_coef: float = 0.0`         # used when method == "aux"
- `deepseek_bias_lr: float = 0.0`      # used when method == "deepseek"
- `deepseek_bias_clip: float = 0.0`    # optional clamp (HALLUCINATION: not in DeepSeek paper; removed in code)
- (optional) `z_loss_coef: float = 0.0` (router logit regularizer)

Derived (no config field):
- `top_k = n_experts // expansion` (equivalently `top_k = granularity`), to keep compute-matching consistent with G/E notation.

Token-choice constraints (config validation):
- `router_activation` must **not** be `softmax_k`.
- `normalization_mode` is ignored (no normalization for token-choice).

Hydra config example (`configs/mlp/scattermoe_tc.yaml`):
```yaml
# @package _global_
model:
  model_type: scattermoe_tc
  router_activation: sigmoid          # keep baseline simple
  # top_k is inferred from granularity/expansion (fanout = G)
  load_balance_method: deepseek       # or: aux / none
  aux_loss_coef: 0.01                 # only if method=aux
  deepseek_bias_lr: 0.01              # only if method=deepseek
  deepseek_bias_clip: 5.0             # HALLUCINATION: not in DeepSeek paper; removed in code
mlp_type_name: scattermoe_tc
```

---

## Parameter layout (packed 2D) + kernel views

Let:
- `C = config.n_embd`
- `E = config.n_experts` (token-choice uses all as routed; no shared expert initially)
- `H = config.expert_dim` (typically `4C / G`)

Parameters (2D, DP-friendly):
```python
self.router = nn.Linear(C, E, bias=False)

# Packed 2D expert weights
# W1 per expert: (H, C)  -> pack as (E*H, C)
self.expert_weight1 = nn.Parameter(torch.empty(E * H, C))

# W2 per expert: (C, H)  -> pack as (E*C, H)
# NOTE: name contains "weight2" so BaseGPT.init_weights() zero-inits it.
self.expert_weight2 = nn.Parameter(torch.empty(E * C, H))
```

Views for ScatterMoE kernels (expect `(E, in, out)`):
```python
# W1: (E, C, H)
W1 = self.expert_weight1.view(E, H, C).permute(0, 2, 1).contiguous()

# W2: (E, H, C)
W2 = self.expert_weight2.view(E, C, H).permute(0, 2, 1).contiguous()
```

---

## Routing + gates (must reuse existing activation util)

**Hard requirement:** router activation follows GEC semantics by calling:
`src/models/router_utils.apply_router_activation`.

Routing/gates snippet (token-choice top-k experts per token):
```python
from src.models.router_utils import apply_router_activation

x_flat = x.view(-1, C)  # (N, C), N=B*T
router_logits_flat = self.router(x).float().view(-1, E)  # (N, E) in fp32

# Activation identical to GEC: apply to ALL logits first (util call), then gather at selected indices.
all_weights, _shared = apply_router_activation(
    router_logits_flat,
    activation=self.config.router_activation,
    G=self.config.granularity,
)  # all_weights: (N, E) for sigmoid/relu/softmax_e*

# DeepSeek mode uses biased scores for *selection* only; weights come from original logits.
selection_logits = router_logits_flat
if self.load_balance_method == "deepseek":
    selection_logits = selection_logits + self.router_bias  # (E,) broadcast

top_k = self.config.n_experts // self.config.expansion  # == granularity
_, expert_idxs = torch.topk(selection_logits, k=top_k, dim=1)  # (N, top_k), int64
gates = torch.gather(all_weights, dim=1, index=expert_idxs)         # (N, top_k)
```

Notes:
- This keeps the “activation then gather” pattern exactly like GEC, just with `dim=1` gather (experts per token).
- **No normalization** for token-choice: do not divide by fanout or use `normalization_mode`.
- `softmax_k` is disallowed for token-choice (validate in config).
- Baseline: `router_activation: sigmoid`.

---

## Kernel preprocessing: permutation metadata

ScatterMoE kernels need:
- `sorted_expert_idxs`: flattened expert ids sorted (length `N*top_k`)
- `sorted_scattered_idxs`: permutation indices mapping back to token-major layout
- `expert_offsets`: cumsum of per-expert counts

We implement our own (repo-style) helper:
```python
def flatten_sort_count(expert_idxs: torch.Tensor, num_experts: int):
    flat = expert_idxs.flatten()  # (N*top_k,)
    sorted_expert_idxs, sorted_scattered_idxs = torch.sort(flat)
    expert_counts = torch.bincount(flat, minlength=num_experts)
    expert_offsets = expert_counts.cumsum(0)
    return sorted_expert_idxs, sorted_scattered_idxs, expert_offsets
```

---

## Kernel wrapper (our own autograd, kernels reused)

Create `src/ops/scattermoe_ops.py` with a custom autograd `Function` that mirrors ScatterMoE’s logic but lives in our tree.

Signature (similar to ScatterMoE, but ours):
```python
def scattermoe_linear(
    x: torch.Tensor,                    # (M, K)
    expert_weights: torch.Tensor,        # (E, K, N)
    k: int,
    sorted_expert_idxs: torch.Tensor,    # (M*k,)
    sorted_scattered_idxs: torch.Tensor, # (M*k,)
    expert_offsets: torch.Tensor,        # (E,)
    *,
    gates: torch.Tensor | None = None,   # (M, k) if provided
    grouped_in: bool = False,
    grouped_out: bool = False,
) -> torch.Tensor:
    ...
```

Forward (kernel call + optional gated reduce):
```python
from scattermoe.scattermoe.kernels import ops as sm_ops

out = sm_ops.scatter2scatter(
    X=x,
    W=expert_weights,
    k=k,
    sorted_expert_idxs=sorted_expert_idxs,
    sorted_scattered_idxs=sorted_scattered_idxs,
    x_grouped=grouped_in,
    y_grouped=grouped_out,
)  # shape: (M*k, N) if k>1 else (M, N)

if gates is not None:
    # out is token-major when grouped_out=False (required for this reshape)
    out_expanded = out.view(gates.size(0), gates.size(1), out.size(-1))  # (M, k, N)
    out = (gates.unsqueeze(1) @ out_expanded).squeeze(1)                # (M, N)
```

Backward (uses ScatterMoE kernels `group` + `group_bwd_W` + `scatter2scatter` for dX):
```python
# 1) If gates used, compute d_gates from saved out_expanded and grad_out
# 2) Group grad_out into expert-major form if grouped_out=False
# 3) Group x into expert-major if grouped_in=False
# 4) Compute dW via sm_ops.group_bwd_W(DY, X, expert_offsets, ...)
# 5) Compute dX via sm_ops.scatter2scatter(DY, W^T, ...) and reduce across fanout if k>1
```

This is a direct translation of ScatterMoE’s autograd strategy, but parameterized for our usage.

---

## MLP forward: two kernel linears + nanochat activation

Create new MLP module `src/models/scattermoe_tc.py`:

```python
class ScatterMoETokenChoiceMLP(BaseMLP):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        C, E, H = config.n_embd, config.n_experts, config.expert_dim
        self.top_k = config.n_experts // config.expansion  # == granularity
        self.load_balance_method = config.load_balance_method

        self.router = nn.Linear(C, E, bias=False)
        self.expert_weight1 = nn.Parameter(torch.empty(E * H, C))
        self.expert_weight2 = nn.Parameter(torch.empty(E * C, H))

        # DeepSeek loss-free bias
        self.register_buffer("router_bias", torch.zeros(E))
        self.register_buffer("bias_count_accum", torch.zeros(E), persistent=False)
        self.register_buffer("bias_count_steps", torch.tensor(0, dtype=torch.long), persistent=False)

    def forward(self, x: torch.Tensor, layer_idx: int = 0):
        B, T, C = x.shape
        N = B * T
        E, H = self.config.n_experts, self.config.expert_dim

        # --- routing + gates (util call) ---
        ... (see routing snippet above) ...

        # --- permutation metadata ---
        sorted_expert_idxs, sorted_scattered_idxs, expert_offsets = flatten_sort_count(expert_idxs, E)

        # --- expert MLP ---
        W1 = self.expert_weight1.view(E, H, C).permute(0, 2, 1).contiguous()  # (E, C, H)
        h = scattermoe_linear(
            x.view(N, C),
            W1,
            k=self.top_k,
            sorted_expert_idxs=sorted_expert_idxs,
            sorted_scattered_idxs=sorted_scattered_idxs,
            expert_offsets=expert_offsets,
            grouped_out=True,
        )  # (N*top_k, H) grouped by expert

        h = F.relu(h).square()  # nanochat ReLU^2

        W2 = self.expert_weight2.view(E, C, H).permute(0, 2, 1).contiguous()  # (E, H, C)
        y = scattermoe_linear(
            h,
            W2,
            k=1,
            sorted_expert_idxs=sorted_expert_idxs,
            sorted_scattered_idxs=sorted_scattered_idxs,
            expert_offsets=expert_offsets,
            gates=gates,
            grouped_in=True,
            grouped_out=False,
        )  # (N, C) token-major, gated sum across top_k

        y = y.view(B, T, C).to(x.dtype)

        metrics = {...}  # tensors only; BaseGPT converts to Python scalars
        return y, metrics
```

---

## Load balancing: aux loss vs DeepSeek bias (both supported)

### A) Aux loss (requires gradients; no `train.py` changes)

Compute inside the MLP forward (tensor):
```python
router_probs = router_logits_flat.softmax(dim=-1)  # (N, E)
mask = torch.zeros_like(router_probs)
mask.scatter_(1, expert_idxs, 1.0 / float(self.top_k))  # (N, E), non-diff in indices (ok)
f = mask.mean(dim=0)          # fraction tokens per expert (soft count)
p = router_probs.mean(dim=0)  # mean router prob per expert (diff)
aux_loss = E * torch.sum(f * p)
```

Return `aux_loss` as a metric **tensor** (e.g. `metrics["aux_loss"] = aux_loss`).

Then, in `BaseGPT.forward`, intercept and add it to CE before `_metrics_to_scalars()`:
```python
aux_loss_total = None
...
aux = block_metrics.pop("aux_loss", None)
if aux is not None:
    aux_loss_total = aux if aux_loss_total is None else aux_loss_total + aux
...
loss = ce_loss
if aux_loss_total is not None and self.config.aux_loss_coef > 0:
    loss = loss + self.config.aux_loss_coef * aux_loss_total
aggregated_metrics["aux_loss"] = aux_loss_total.detach()
```

Result:
- Backprop uses the combined loss without touching `train.py`.
- Logging gets scalar aux loss as usual.

### B) DeepSeek loss-free bias update (no aux loss)

Forward:
- selection uses `selection_logits = router_logits + router_bias`
- gating weights still come from `apply_router_activation(router_logits)` (unbiased) gathered at the selected indices.

Per-step update:
- accumulate counts each forward micro-step:
```python
with torch.no_grad():
    counts = torch.bincount(expert_idxs.flatten(), minlength=E).to(self.bias_count_accum.dtype)
    self.bias_count_accum.add_(counts)
    self.bias_count_steps.add_(1)
```

- at step boundary (hooked from `BaseGPT.step_complete`), update bias once:
```python
def finalize_bias_update(self):
    if self.bias_count_steps.item() == 0:
        return
    counts = self.bias_count_accum
    if dist.is_initialized():
        dist.all_reduce(counts, op=dist.ReduceOp.SUM)
    counts = counts / float(self.bias_count_steps.item())
    target = counts.mean()
    delta = self.config.deepseek_bias_lr * torch.sign(target - counts)
    self.router_bias.add_(delta)
    if self.config.deepseek_bias_clip > 0:  # HALLUCINATION: not in DeepSeek paper; removed in code
        self.router_bias.clamp_(-self.config.deepseek_bias_clip, self.config.deepseek_bias_clip)
    self.bias_count_accum.zero_()
    self.bias_count_steps.zero_()
```

This requires a small, clean hook in `BaseGPT.step_complete`:
```python
for block in self.blocks:
    finalize = getattr(block.mlp, "finalize_bias_update", None)
    if callable(finalize):
        finalize()
```

---

## Minimizing `train.py` modifications

Preferred approach (clean + minimal):
- **Do not modify `train.py` at all.**
- Combine CE + aux loss inside `BaseGPT.forward` (model code), because `train.py` expects metrics to be Python types and cannot backprop through them.

Fallback approach (if you explicitly want `train.py` to own loss composition):
- Add `ModelOutput.aux_loss: Optional[Tensor]` and sum in train loop.
- This is still a small change, but it touches training loop, so it’s not the minimal path.

---

## Implementation checklist (concrete steps)

1) **New ops wrapper**
   - Add `src/ops/scattermoe_ops.py`:
     - `flatten_sort_count` helper (torch ops)
     - `ScatterMoEParallelLinear` autograd.Function
     - `scattermoe_linear(...)` convenience wrapper

2) **New MLP module**
   - Add `src/models/scattermoe_tc.py`:
     - packed params: `router`, `expert_weight1`, `expert_weight2`
     - forward path (two linears + ReLU²)
     - routing activation via `apply_router_activation` (hard requirement)
     - metrics (tensor)
     - aux loss (optional) + deepseek accumulation buffers (optional)

3) **Model type wiring**
   - Update `src/models/model_base.py`:
     - allow new `model_type`
     - route `_get_mlp_class()` to import `ScatterMoETokenChoiceMLP`
   - Update `src/config.py` validation allowlist:
     - disallow `router_activation=softmax_k` for `scattermoe_tc`
     - reject or ignore `normalization_mode` (token-choice uses raw gates)
   - Add `configs/mlp/scattermoe_tc.yaml`
   - Update `configs/config.yaml` docs if needed

4) **Aux loss plumbing (no train.py change)**
   - Update `src/models/model_base.py` (`BaseGPT.forward`) to:
     - accumulate per-layer `aux_loss` tensors
     - add to CE using `aux_loss_coef`
     - log detached scalar metric

5) **DeepSeek bias update hook**
   - Update `src/models/model_base.py` (`BaseGPT.step_complete`) to call optional `finalize_bias_update()` on MLPs.

6) **Tests**
   - Add CUDA-only test comparing:
     - forward output parity vs a naive reference implementation
     - backward (grad) parity for `expert_weight1/2` and router
   - Add a smoke test: build `BaseGPT` with `model_type=scattermoe_tc` and run a single forward pass.
   - Run `test/test_weight_init.py` after adding new params (ensures naming/init conventions are respected).

---

## Acceptance criteria

- `python train.py +experiment=debug mlp=scattermoe_tc` runs on single GPU.
- `torchrun --nproc_per_node=2 train.py +experiment=debug mlp=scattermoe_tc` runs (DP/DDP), no divergence/deadlocks.
- Aux loss mode:
  - `load_balance_method=aux` produces nonzero `aux_loss` metric and gradients flow.
- DeepSeek mode:
  - `load_balance_method=deepseek` updates `router_bias` over time (logged) without aux loss.
- GPU tests pass (and CPU skips cleanly when CUDA unavailable).
