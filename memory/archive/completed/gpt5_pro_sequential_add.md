Below I do three things:

1. **Audit your kernel and the `build_slot_indices` helper** for functional correctness and common corner cases.
2. **Provide custom autograd ops** for CSR‑gather and CSR‑scatter‑reduce built around your Triton kernel, with correct gradients (including `grad_w` when per‑slot weights are used).
3. **Rewrite `forward_topk`** in your `GECSharedMLP` to use the custom ops end‑to‑end, while keeping your math (router activation, normalizer, metrics) intact.

I keep the terminology consistent:

* **Tokens**: rows of the `(N, H)` buffer (flattened from `(B, T, H)`)
* **Experts**: routed experts, `E = n_routed_experts`
* **Capacity**: per‑expert selection count `C` (your `k`), so the expert-major buffer has shape `(E*C, H)`
* **CSR** for tokens: we represent contributors to each token with `(slot_indices, slot_offsets, slot_counts)` as you already do

---

## 1) Kernel audit

### `build_slot_indices(indices, num_tokens, max_experts)`

Assumed input shape: **`indices` is `(E, C)`** where `indices[e, s]` is the token id routed to expert `e` at capacity slot `s`, or `-1` if empty. Your docstring example shows a `topk` that returns `(N, K)`; that is token‑major and does **not** match the function’s expected layout. As long as the caller provides `(E, C)` (expert‑major), your function is consistent.

Key points:

* You flatten `(E, C)` and keep only valid token ids, then **stable sort by token id**. Stability preserves the expert/capacity order within the same token, which makes later deterministic drops predictable.
* You cap per‑token contributors at `max_experts` using the `slot` trick. That cap is important for the Triton kernel's `MAX_EXPERTS` compile‑time bound.
* You compute:

  * `slot_counts[t]` = number of kept contributions to token `t`
  * `slot_offsets[t]` = starting offset in `slot_indices` where token `t`'s contributions live
  * `slot_indices` = linear indices in the expert‑major flattened space `(E*C)` for kept contributions
* Edge cases (`no valid tokens`, `num_tokens = 0`) are handled.

This helper is **functionally correct** for the intended CSR build.

### `_csr_scatter_sum` Triton kernel

**Behavior**: For each token `pid`, you sum contributions from at most `MAX_EXPERTS` expert rows (selected via `slot_indices`) across the hidden dimension, optionally scaling each slot by a per‑slot scalar `weights[lin]`. You optionally **add into** an existing buffer.

**Correctness notes:**

* The launch grid must be `(N,)` so `pid ∈ [0, N)`. `slot_offsets` and `slot_counts` are length `N`. Good.
* You guard the `slot_indices` load with `slot_mask = slot_ids < count`. This prevents any out‑of‑bounds dereference for the last token (where `start + MAX_EXPERTS - 1` could exceed `K-1`), because masked loads in Triton do not dereference inactive lanes.
* The hidden dimension loop `for col in range(0, NUM_COLUMNS, BLOCK_X)` is fine because `NUM_COLUMNS` is `constexpr`. The tail is correctly masked by `col_mask`.
* Accumulator is FP32, store casts back to `token_out.dtype.element_ty` (so BF16 is respected). This is standard.
* When `count = 0`, `slot_mask` is all false. Loads are masked off and you write zeros (or keep previous if `ACCUMULATE=1` and you loaded it) as expected.
* `USE_WEIGHTS`: You only touch `w` inside `if USE_WEIGHTS:` branches, so passing a dummy pointer when not used is fine.

**Performance and robustness hints (not blockers):**

* **`MAX_EXPERTS` should be a small, realistic upper bound** on per‑token fan‑in; setting it to `E` when `E` is large wastes registers and bandwidth. The CSR builder already hard‑caps to `max_experts`, so pass the same value to the kernel.
* Make sure `expert_slots` and `token_out` are contiguous and 128‑bit aligned if possible. Triton does not require it, but it helps on NVIDIA.
* The kernel’s math is bandwidth‑bound for large `H`; autotuning `BLOCK_X` at `[64, 128, 256]` with `num_warps` in `{2,4}` is a good baseline.

**Conclusion**: The kernel and CSR builder are **correct** for the documented use.

---

## 2) Custom autograd ops for CSR‑gather and CSR‑scatter‑reduce

We implement two autograd Functions:

* **`CSRGather`**:

  * **forward**: simple index lookup `y[e, s, :] = x[indices[e, s], :]` (zeros where `indices == -1`)
  * **backward**: scatter‑reduce **sum** of `grad_y` back to tokens using **the Triton kernel**

* **`CSRScatter`** (scatter‑reduce in forward):

  * **forward**: the Triton kernel to sum `expert_slots[e, s, :]` into tokens, with optional per‑slot weights `w[e, s]`
  * **backward**: simple index gather of `grad_out[t, :]` back to each slot `grad_a[e, s, :]`, multiplied by `w[e, s]` if provided; plus `grad_w[e, s] = dot(expert_slots[e, s, :], grad_out[token, :])`

Both ops share the same CSR build helper.

> Implementation notes:
>
> * We keep the **internal** expert‑major buffers as **flattened** `(E*C, H)` for the Triton call.
> * For user ergonomics, `CSRGather` returns `(E, C, H)` so you can call batched GEMMs as in your current code.
> * Gradients:
>
>   * `CSRGather.backward` computes `grad_x ∈ ℝ^{N×H}` via `_csr_scatter_sum` with `USE_WEIGHTS=0`.
>   * `CSRScatter.backward` returns `grad_a ∈ ℝ^{E*C×H}` via a masked gather of `grad_out[indices]` times `w`, and `grad_w ∈ ℝ^{E*C}` via row‑wise dot products when `w` is present and requires grad.

### Full code (drop‑in)

```python
# --- csr_ops.py --------------------------------------------------------------
import torch
import triton
import triton.language as tl
from typing import Optional, Tuple

# ---------- CSR builder (your function, kept as-is with small edits) ----------
@torch.no_grad()
def build_slot_indices(indices: torch.Tensor, num_tokens: int, max_experts: int
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    indices: int32/int64 [E, C] with token ids or -1
    returns:
      slot_indices: int32 [K]   (linear ids in E*C space; K=sum slot_counts)
      slot_offsets:   int32 [N]   (start of each token's slice in slot_indices)
      slot_counts:   int32 [N]   (#contributors per token)
    """
    assert indices.dim() == 2
    E, C = indices.shape
    device = indices.device

    token_flat = indices.reshape(-1).to(torch.int64)                                   # (E*C,)
    linear_flat = torch.arange(E * C, device=device, dtype=torch.int64)                # (E*C,)

    valid = (token_flat >= 0) & (token_flat < num_tokens)
    token_flat = token_flat[valid]
    linear_flat = linear_flat[valid]

    if token_flat.numel() == 0:
        slot_indices = torch.empty(0, dtype=torch.int32, device=device)
        slot_offsets = torch.zeros(num_tokens, dtype=torch.int32, device=device)
        slot_counts = torch.zeros(num_tokens, dtype=torch.int32, device=device)
        return slot_indices, slot_offsets, slot_counts

    sort_idx = torch.argsort(token_flat, stable=True)
    token_flat = token_flat[sort_idx]
    linear_flat = linear_flat[sort_idx]

    # per-token cap to max_experts
    is_new = torch.ones_like(token_flat, dtype=torch.bool)
    is_new[1:] = token_flat[1:] != token_flat[:-1]
    starts = torch.where(is_new)[0]
    gid = torch.searchsorted(starts, torch.arange(token_flat.numel(), device=device), right=True) - 1
    slot = torch.arange(token_flat.numel(), device=device) - starts[gid]
    keep = slot < max_experts
    token_flat = token_flat[keep]
    linear_flat = linear_flat[keep]

    slot_counts = torch.bincount(token_flat, minlength=num_tokens).to(torch.int32)
    if num_tokens > 0:
        c64 = slot_counts.to(torch.int64)
        prefix = torch.cumsum(c64, dim=0)
        slot_offsets = (prefix - c64).to(torch.int32)
    else:
        slot_offsets = torch.empty(0, dtype=torch.int32, device=device)

    slot_indices = linear_flat.to(torch.int32)
    return slot_indices, slot_offsets, slot_counts


# ---------- Triton kernel (your code, unchanged) ----------
@triton.autotune(
    configs=[
        triton.Config({'BLOCK_X': 64}, num_warps=2),
        triton.Config({'BLOCK_X': 128}, num_warps=2),
        triton.Config({'BLOCK_X': 256}, num_warps=2),
        triton.Config({'BLOCK_X': 128}, num_warps=4),
        triton.Config({'BLOCK_X': 256}, num_warps=4),
    ],
    key=['NUM_COLUMNS', 'MAX_EXPERTS'],
)
@triton.jit
def _csr_scatter_sum(
    expert_slots,      # bf16: flattened (E*C, H)
    token_out,         # bf16: (N, H)
    slot_indices,      # int32: (K,)
    slot_offsets,      # int32: (N,)
    slot_counts,       # int32: (N,)
    weights,           # bf16: (E*C,) optional; ignored if USE_WEIGHTS == 0
    MAX_EXPERTS: tl.constexpr,
    NUM_COLUMNS: tl.constexpr,
    BLOCK_X: tl.constexpr,
    USE_WEIGHTS: tl.constexpr,    # 0 or 1
    ACCUMULATE: tl.constexpr, # 0 or 1
):
    pid = tl.program_id(0)  # token id
    start = tl.load(slot_offsets + pid)
    count = tl.load(slot_counts + pid)

    slot_ids = tl.arange(0, MAX_EXPERTS)
    slot_mask = slot_ids < count

    lins = tl.load(slot_indices + start + slot_ids, mask=slot_mask, other=0)
    bases = lins * NUM_COLUMNS
    if USE_WEIGHTS:
        w = tl.load(weights + lins, mask=slot_mask, other=0.0).to(tl.float32)

    col_ids = tl.arange(0, BLOCK_X)
    token_row = token_out + pid * NUM_COLUMNS

    for col in range(0, NUM_COLUMNS, BLOCK_X):
        offs = col + col_ids
        col_mask = offs < NUM_COLUMNS
        out_ptr = token_row + offs

        if ACCUMULATE:
            acc = tl.load(out_ptr, mask=col_mask, other=0).to(tl.float32)
        else:
            acc = tl.zeros([BLOCK_X], dtype=tl.float32)

        ptrs = expert_slots + bases[:, None] + offs[None, :]
        m = slot_mask[:, None] & col_mask[None, :]

        x = tl.load(ptrs, mask=m, other=0.0).to(tl.float32)
        if USE_WEIGHTS:
            x = x * w[:, None]
        acc += tl.sum(x, axis=0)

        tl.store(out_ptr, acc.to(token_out.dtype.element_ty), mask=col_mask)


# ---------- Autograd wrappers ----------
class CSRGather(torch.autograd.Function):
    """
    Forward: y[e, s, :] = x[indices[e, s], :] (zeros if indices == -1).
    Backward: grad_x = scatter-reduce(sum) of grad_y by token using _csr_scatter_sum.
    """
    @staticmethod
    def forward(ctx, x_tokens: torch.Tensor, indices: torch.Tensor, max_experts: int):
        # x_tokens: (N, H), indices: (E, C)
        assert x_tokens.dim() == 2 and indices.dim() == 2
        N, H = x_tokens.shape
        E, C = indices.shape
        device = x_tokens.device
        dtype = x_tokens.dtype

        flat = indices.reshape(-1)  # (E*C,)
        mask = flat >= 0
        y_flat = torch.zeros(E * C, H, device=device, dtype=dtype)
        if mask.any():
            y_flat[mask] = x_tokens[flat[mask]]
        y = y_flat.view(E, C, H)

        # Build CSR once and save for backward
        slot_idx, slot_offs, counts = build_slot_indices(indices, num_tokens=N, max_experts=max_experts)
        # Save tensors for backward
        ctx.save_for_backward(indices.to(torch.int32), slot_idx, slot_offs, counts)
        ctx.N = N
        ctx.H = H
        ctx.max_experts = max_experts
        return y

    @staticmethod
    def backward(ctx, grad_y: torch.Tensor):
        # grad_y: (E, C, H) -> need grad_x: (N, H)
        indices, slot_idx, slot_offs, counts = ctx.saved_tensors
        E, C, H = grad_y.shape
        assert H == ctx.H
        device = grad_y.device
        dtype = grad_y.dtype

        grad_y2d = grad_y.reshape(E * C, H).contiguous()
        grad_x = torch.zeros(ctx.N, H, device=device, dtype=dtype)

        # Dummy weights (unused): shape >=1
        dummy_w = torch.empty(1, device=device, dtype=dtype)

        # Launch: USE_WEIGHTS=0, ACCUMULATE=0
        grid = (ctx.N,)
        _csr_scatter_sum[grid](
            grad_y2d, grad_x,
            slot_idx, slot_offs, counts, dummy_w,
            MAX_EXPERTS=ctx.max_experts,
            NUM_COLUMNS=H,
            USE_WEIGHTS=0,
            ACCUMULATE=0
        )
        return grad_x, None, None  # only x_tokens has grad


class CSRScatter(torch.autograd.Function):
    """
    Forward: out_tokens = sum_{slots->token} ( w[l] * expert_slots[l, :] ) using Triton kernel.
             If weights is None, w[l] = 1.
    Backward:
      grad_a[l, :] = w[l] * grad_out[token_of_l, :]
      grad_w[l]    = dot(expert_slots[l, :], grad_out[token_of_l, :])   (if weights requires_grad)
    """
    @staticmethod
    def forward(ctx,
                a_slots: torch.Tensor,       # (E*C, H)
                indices: torch.Tensor,       # (E, C) token ids or -1
                weights: Optional[torch.Tensor],  # (E*C,) or None
                num_tokens: int,
                max_experts: int,
                add_into: bool = False
               ):
        assert a_slots.dim() == 2 and indices.dim() == 2
        E, C = indices.shape
        E_times_C, H = a_slots.shape
        assert E_times_C == E * C, "a_slots must be flattened (E*C, H)"
        device = a_slots.device
        dtype = a_slots.dtype

        out = torch.zeros(num_tokens, H, device=device, dtype=dtype)

        slot_idx, slot_offs, counts = build_slot_indices(indices, num_tokens=num_tokens, max_experts=max_experts)

        # Set up weights
        USE_WEIGHTS_VAL = 1 if weights is not None else 0
        if USE_WEIGHTS_VAL:
            assert weights.shape == (E * C,), "weights must be (E*C,)"
            w_use = weights
        else:
            # Triton signature needs a pointer; pass a dummy tensor
            w_use = torch.empty(1, device=device, dtype=dtype)

        # Save for backward: keep inputs minimal to reduce memory
        save_a_for_grad_w = (weights is not None) and weights.requires_grad
        if save_a_for_grad_w:
            ctx.save_for_backward(indices.to(torch.int32), weights, a_slots)
        else:
            ctx.save_for_backward(indices.to(torch.int32),)
        ctx.has_weights = USE_WEIGHTS_VAL == 1
        ctx.num_tokens = num_tokens
        ctx.max_experts = max_experts
        ctx.H = H

        grid = (num_tokens,)
        _csr_scatter_sum[grid](
            a_slots, out,
            slot_idx, slot_offs, counts, w_use,
            MAX_EXPERTS=max_experts,
            NUM_COLUMNS=H,
            USE_WEIGHTS=USE_WEIGHTS_VAL,
            ACCUMULATE=1 if add_into else 0
        )
        return out

    @staticmethod
    def backward(ctx, grad_out: torch.Tensor):
        # grad_out: (N, H)
        saved = ctx.saved_tensors
        if ctx.has_weights and len(saved) == 3:
            indices, weights, a_slots = saved
        else:
            indices = saved[0]
            weights = None
            a_slots = None

        N, H = grad_out.shape
        E, C = indices.shape
        device = grad_out.device

        flat = indices.reshape(-1)                              # (E*C,)
        mask = flat >= 0
        # Gather grad_out to slots
        gathered = torch.zeros(E * C, H, device=device, dtype=grad_out.dtype)
        if mask.any():
            gathered_rows = grad_out[flat[mask]]                # (#valid, H)
            if weights is not None:
                gathered_rows = gathered_rows * weights[mask].unsqueeze(1)
            gathered[mask] = gathered_rows

        grad_a = gathered
        # grad_weights if needed
        grad_w = None
        if weights is not None and a_slots is not None and torch.is_grad_enabled() and weights.requires_grad:
            grad_w = torch.zeros_like(weights)
            if mask.any():
                # dot over H: sum_j a[l, j] * grad_out[token_of_l, j]
                dots = (a_slots[mask] * grad_out[flat[mask]]).sum(dim=1)
                grad_w[mask] = dots

        # No gradients for indices, num_tokens, max_experts, add_into
        if weights is None:
            return grad_a, None, None, None, None, None
        else:
            return grad_a, None, grad_w, None, None, None


# ---------- Convenience wrappers ----------
def csr_gather(x_tokens: torch.Tensor, indices: torch.Tensor, max_experts: int) -> torch.Tensor:
    """
    x_tokens: (N, H)
    indices:  (E, C)
    returns:  (E, C, H)
    """
    return CSRGather.apply(x_tokens, indices, max_experts)


def csr_scatter_sum(a_slots_2d: torch.Tensor, indices: torch.Tensor,
                    num_tokens: int, max_experts: int,
                    weights_flat: Optional[torch.Tensor] = None,
                    add_into: bool = False) -> torch.Tensor:
    """
    a_slots_2d: (E*C, H)
    indices:    (E, C)
    weights_flat: (E*C,) or None
    returns: out_tokens (N, H)
    """
    return CSRScatter.apply(a_slots_2d, indices, weights_flat, num_tokens, max_experts, add_into)
```

**Sanity checks to keep in mind**

* `indices.dtype` can be `int32` or `int64`. The autograd functions cast saved `indices` to `int32` for the Triton calls. The gather/scatter outside Triton accept either.
* When you supply `weights`, its length must be `E*C` and it should already reflect any **per‑token** scaling you want (for example division by a token‑level normalizer). The kernel multiplies each slot by `w[l]` and sums.

---

## 3) Rewrite of `forward_topk` using the custom ops

The changes are:

* Keep your router, top‑k, and shared expert path.
* Build **expert‑major** `indices ∈ ℤ^{E×C}` directly from the top‑k results (`C = k` from your code).
* Use `csr_gather(x_flat, indices, max_experts)` instead of advanced indexing and reshaping.
* Compute the routed expert MLP in the same batched way you already do.
* Compute router activation `weights` and the **token normalizer** exactly as you already do.
* Build **per‑slot weights** for the scatter as `w_flat = router_weights / normalizer[t_of_slot]`.
* Call `csr_scatter_sum(h_flat, indices, num_tokens, max_experts, w_flat)` to write the routed output.
* Normalize and add the shared expert output.

You also get correct gradients through `weights` into the router, because `CSRScatter` returns `grad_w`.

> Choosing `max_experts`:
>
> * For **top‑k per expert**, the maximum contributors per token can be as high as `E` in the worst case. For performance, set a reasonable cap such as `max_experts = getattr(self.config, "moe_max_fanout", min(self.n_routed_experts, 32))`. The CSR builder will **drop deterministically** beyond this cap, matching the intended semantics of your cap.

Here is a drop‑in replacement for `forward_topk` that uses the new ops. It keeps your normalizer and metrics logic intact, and it preserves types under autocast.

```python
# --- model_forward_topk_fast.py (inside class GECSharedMLP) -------------------
import torch
import torch.nn.functional as F

# Assume csr_ops is importable
from .csr_ops import csr_gather, csr_scatter_sum

def forward_topk(self, x: torch.Tensor, layer_idx: int = 0):
    """Forward pass with global top-k routing using CSR custom ops."""
    B, T, C = x.shape
    n_routed_experts = self.n_routed_experts
    N = B * T  # number of tokens
    H = C      # hidden/embedding dim

    # Shared expert on all tokens
    x_flat = x.view(-1, C)
    shared_h = F.linear(x_flat, self.shared_weight1)
    shared_h = F.relu(shared_h).square()
    shared_output = F.linear(shared_h, self.shared_weight2)  # (N, C)

    # Router scores and global top-k per expert
    router_logits = self.router(x)                           # (B, T, E)
    router_logits_flat = router_logits.view(-1, n_routed_experts)  # (N, E)

    # Compute k exactly as you do now
    G = self.config.granularity
    E = self.config.expansion
    k = int(N * (G - 1) // (G * E))
    k = max(0, min(k, N))  # safety

    # topk over tokens for each expert -> (E, k)
    # We transpose so experts are rows
    topk_values, topk_indices = torch.topk(router_logits_flat.t(), k=k, dim=1)  # (E, k)

    # Moving EMA of cutoffs (last selected score per expert)
    cutoffs = topk_values[:, -1] if k > 0 else torch.zeros(n_routed_experts, device=x.device, dtype=router_logits.dtype)
    with torch.no_grad():
        self.cutoff_ema = self.ema_decay * self.cutoff_ema + (1 - self.ema_decay) * cutoffs
        self.cutoff_ema_count += 1

    # Expert-major indices: (E, C) with C=k here. No -1 padding is needed because k tokens per expert.
    indices = topk_indices  # shape (E, k)
    E_, C_ = indices.shape
    assert E_ == n_routed_experts and C_ == k

    # Choose a practical cap on per-token contributors for kernel compile-time bound
    max_fanout = getattr(self.config, "moe_max_fanout", min(n_routed_experts, 32))

    # Gather tokens for experts: (E, k, C)
    x_ekc = csr_gather(x_flat, indices, max_experts=max_fanout)  # (E, k, C)

    # Expert MLP in batch: stack weights as in your original code
    weight1_3d = torch.stack([w for w in self.expert_weight1])           # (E, D_hidden, C)
    weight2_3d = torch.stack([w for w in self.expert_weight2])           # (E, C, D_hidden)

    # First linear: (E, k, C) x (E, C, D_hidden)^T -> (E, k, D_hidden)
    h = torch.bmm(x_ekc, weight1_3d.transpose(1, 2))
    h = F.relu(h).square()
    # Second linear: (E, k, D_hidden) x (E, D_hidden, C)^T -> (E, k, C)
    h = torch.bmm(h, weight2_3d.transpose(1, 2))

    # Router activation weights per slot (E, k)
    slot_weights = self.apply_router_activation(topk_values, self.config.router_activation)  # (E, k)

    # Build token-level normalizer the same way you already do
    permutation_indices = indices.reshape(-1)  # (E*k,)
    normalizer = self.compute_normalizer(
        mode=self.config.normalization_mode,
        n_tokens=N,
        indices=permutation_indices,
        weights=slot_weights.reshape(-1),
        router_logits_flat=router_logits_flat,
        router_activation=self.config.router_activation,
        device=x.device,
        baseline=0.0
    )  # (N,)

    # Add 1.0 for the shared expert
    normalizer = normalizer + 1.0

    # Prepare per-slot weights for scattering: divide by normalizer[token_of_slot]
    #   w_flat[i] = slot_weights[i] / normalizer[token_of_slot[i]]
    # indices[e, s] is the token id; use it to normalize
    token_norm_for_slots = normalizer[indices]                     # (E, k)
    slot_weights_normed = slot_weights / token_norm_for_slots      # (E, k)
    weights_flat = slot_weights_normed.reshape(-1).contiguous()    # (E*k,)

    # Flatten expert outputs to (E*k, C) for the scatter kernel
    h_flat = h.reshape(-1, C).contiguous()

    # Scatter-reduce into routed_output
    routed_output = csr_scatter_sum(
        h_flat, indices,
        num_tokens=N,
        max_experts=max_fanout,
        weights_flat=weights_flat,
        add_into=False
    )  # (N, C)

    # Normalize shared output once (same normalizer)
    shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)

    # Combine
    output = shared_output + routed_output
    output = output.view(B, T, C)

    # Metrics: mirror your original logic
    token_fanout = torch.zeros(N, device=x.device)
    ones = torch.ones(len(permutation_indices), device=x.device)
    token_fanout.scatter_add_(0, permutation_indices, ones)

    expert_token_counts = torch.full((n_routed_experts,), k, device=x.device)

    total_expert_usage = torch.cat([
        torch.ones(1, device=x.device),                   # shared expert
        expert_token_counts / N
    ])
    token_fanout_with_shared = token_fanout + 1.0

    metrics = self.compute_routing_metrics(
        cutoffs=cutoffs,
        cutoff_ema=self.cutoff_ema.clone(),  # type: ignore
        weights=slot_weights.reshape(-1),
        router_logits_flat=router_logits_flat,
        token_fanout=token_fanout_with_shared,
        expert_usage=total_expert_usage,
        layer_idx=layer_idx,
        n_layer=self.config.n_layer,
        model_instance=self,
        router_activation=self.config.router_activation,
        normalizer=normalizer,
        indices=permutation_indices,
        normalization_mode=self.config.normalization_mode,
    )

    if not torch.is_grad_enabled():
        metrics['layer_data'] = {
            'weights': slot_weights.reshape(-1).detach(),
            'fanout': token_fanout_with_shared.detach(),
            'cutoffs': cutoffs.detach(),
            'router_logits': router_logits_flat.detach(),
        }

    return output, metrics
```

### Notes on numerical behavior and shapes

* The **normalizer** is identical to your original implementation. The only change is **where** the division happens: we push `(1 / normalizer[token])` into `weights_flat` so the kernel can keep a simple multiply‑accumulate form.
* `CSRScatter.backward` produces `grad_w` which flows back to the router through `slot_weights = f(router_logits)`; PyTorch will handle that chain.
* If you need **`ACCUMULATE=True`** (for example, accumulating routed into an existing buffer), you can pass `add_into=True` to `csr_scatter_sum`. In your presented `forward_topk`, you do not need it; you sum with the shared output afterward.
* If you expect rare but possible very large token fan‑ins, increase `moe_max_fanout` in the config. The CSR builder drops contributors above the cap in a deterministic way (stable order), which matches how you document the cap.

### About the `k` formula

Your comment says:

> Formula: `k = n_tokens × (G-1) // (G×E)` ensures `G-1` routed experts active per token.

The average number of routed experts per token is actually `(E*k)/N ≈ (G-1)/G` with that formula, which is **independent of `E`** and less than 1 if `G>1`. If the intention is an average of `G-1` routed experts **per token**, the usual formula would be `k = floor( (G-1) * N / E )`. I did **not** alter your code, but I wanted to flag the mismatch between the comment and the arithmetic.

---

## Why this helps

* **One read, one write, no atomics** is preserved. Each token program in Triton reads at most `MAX_EXPERTS` rows, streams across `H` in wide stripes, and writes once.
* **Backward reuse**: The gradient for gather uses the same kernel, which avoids a second custom Triton path.
* **Router gradients**: Passing `weights_flat` through `CSRScatter` produces a clean `grad_w`, which backpropagates into the router without any extra code.
* **Memory**: The only large temporary you allocate for routing is the expert‑major buffer `(E*k, H)` as in your original path. There is no additional `(N, #fan_in)` scratch.

---

### Minimal usage sketch (for unit testing)

```python
# x_tokens: (N, H)
# indices:  (E, C) token ids (use -1 to test padding)
# a_slots:  (E*C, H) expert outputs to scatter

# Gather then scatter should act like identity if a_slots = gathered and weights=1
y = csr_gather(x_tokens, indices, max_experts=32)  # (E, C, H)
y2d = y.view(-1, x_tokens.shape[1])
out = csr_scatter_sum(y2d, indices, num_tokens=x_tokens.shape[0], max_experts=32, weights_flat=None)
# out should equal x_tokens aggregated by the number of times each token appears in indices
```

You can also run `torch.autograd.gradcheck` on both `CSRGather` and `CSRScatter` with small tensors in `float64` to verify gradients numerically (wrap BF16 paths with casts just for gradcheck).

---

If you want, I can add a small micro‑benchmark harness with random `E, C, N, H` to compare `index_add_` versus `csr_scatter_sum` on your GPU.
