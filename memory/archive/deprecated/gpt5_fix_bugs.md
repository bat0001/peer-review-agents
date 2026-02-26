# GEC_shared Normalization Bug Fix Notes

**Status**: ⚠️ ARCHIVED - Deprecated
**Date**: October 2025
**Note**: Bug fix notes for GEC_shared normalization. Archive reason: Implementation-specific debugging notes, not a formal plan.

---

**Original Debugging Notes:**

Short answer: you are dividing the shared‑expert path by a denominator that was computed **only from routed experts**, so for tokens that get few or zero routed selections the denominator is ~0. After the `clamp(min=1e-6)` this turns into a huge amplification of the shared path, which quickly explodes the activations and gives NaN gradients. Your dense MLP never does this division, so it trains fine.

In your `gec_shared` training path (`forward_topk`), you build a per‑token normalizer from the routed selections (fan‑out or sum of selected weights), then you apply it to both the routed and the shared outputs. The key lines are (showing the relevant pattern):

```python
# h already normalized per selected token:
normalizer_h = normalizer[permutation_indices].view(n_routed_experts, k, 1).to(h.dtype)
h = h * weights / normalizer_h
...
# ↓ This divides the always-on shared path by a routed-only normalizer
shared_output = shared_output / normalizer.unsqueeze(-1).to(shared_output.dtype)
output = shared_output + routed_output
```

By contrast, your eval/threshold path uses a denominator that **includes the shared expert**:

```python
# counts = routed_expert_count_per_token
normalizer = (counts + 1.0).clamp(min=1e-6).unsqueeze(-1)
output = (shared_output + routed_output) / normalizer
```

So training and eval are inconsistently scaled. When batch×sequence is small or `G` and `E` make `k = ⌊(B·T)·(G−1)/(G·E)⌋` small, many tokens get 0 routed selections; then `normalizer≈0` and the shared path division blows up.

Two safe fixes (pick one):

1. **Do not normalize the shared path.** Normalize only the routed part; then add the shared output as is. This is the simplest and numerically stable.

```python
# After computing `normalizer` for routed tokens:
normalizer_h = normalizer[permutation_indices].view(n_routed_experts, k, 1).to(h.dtype)
h = h * weights / normalizer_h

# Scatter routed contributions
routed_output = torch.zeros_like(x_flat)
routed_output.index_add_(0, permutation_indices, h)

# Do NOT divide the shared path by the routed-only normalizer
output = shared_output + routed_output
```

2. **If you do want “average over shared+routed”, include the shared term in the denominator.** Mirror your eval logic during training:

```python
# Build a denominator that includes the always-on shared expert
denom_total = (normalizer + 1.0)                      # length = n_tokens
denom_total = denom_total.unsqueeze(-1).to(shared_output.dtype)

# Normalize routed contributions by routed-only counts/weights:
normalizer_h = (normalizer[permutation_indices].view(n_routed_experts, k, 1)).to(h.dtype)
h = h * weights / normalizer_h
routed_output = torch.zeros_like(x_flat)
routed_output.index_add_(0, permutation_indices, h)

# Normalize the sum using the shared-inclusive denominator
output = (shared_output + routed_output) / denom_total
```

Either change prevents the “divide shared by ~0” amplification that leads to NaNs.

Two additional guardrails that help in practice:

• **Ensure `k ≥ 1`.** With your current formula `k = int((B·T)·(G−1)/(G·E))`, small microbatches can produce `k=0`, which also breaks the “cutoff = topk_values[:, -1]” line and makes normalizers degenerate. Use

```python
raw = (n_tokens * (G - 1)) / (G * E)
k = max(1, int(math.ceil(raw)))
k = min(k, n_tokens)
```

You still can have tokens with zero selections (top‑k per expert does not guarantee coverage per token), but you will not hit empty selections per expert.

• **Clip the denominator used on the shared path to ≥1.0 if you keep dividing it.** If you choose to keep a shared‑inclusive denominator, use `denom_total.clamp_min(1.0)` so you never amplify the shared path above its natural scale.

Why this shows up only in `gec_shared`: the dense MLP output is never divided by a data‑dependent tiny scalar, so its scale stays bounded by standard initialization and LN. In `gec_shared`, the shared branch is divided by a routed‑only normalizer that can be arbitrarily small; a few steps later the residual stream overflows and backprop yields NaN.

If you want a quick confirmation, log the minima before the division in training:

```python
with torch.no_grad():
    bad = (normalizer == 0)
    if bad.any():
        print("tokens with zero routed selections:", bad.sum().item())
    print("min normalizer:", float(normalizer.min()))
```

and you will see zeros whenever batch×sequence is small or your router is early in training.

If you want me to propose the exact patch inline against your `shared.py` around the `forward_topk` normalization block, I can write it out based on which of the two options you prefer.

---

You are right that “shared expert + normalizer += 1” can fix this—but in your code the “+1” is only used in the **eval/threshold** path. In the **training/top-k** path you still divide the shared branch by a denominator that was computed **only from routed selections** (no “+1”), so tokens with few or zero routed hits get an ~0 denominator and the shared branch is blown up → NaNs.

### What to change

You have two clean choices. Pick one.

#### A) Do **not** divide the shared branch at all (simplest, stable)

Keep routed-path normalization as is; add the shared output without any division.

```python
# routed normalization (unchanged)
normalizer_h = normalizer[perm].view(n_routed_exp, k, 1).to(h.dtype)
h = h * weights / normalizer_h

routed_out = torch.zeros_like(x_flat)
routed_out.index_add_(0, perm, h)

# shared branch: DO NOT divide by `normalizer`
out = shared_out + routed_out
```

#### B) If you want an “average over (shared + routed)”, include shared in the denominator

Mirror your eval logic during training and apply the “+1” **only** to the final per-token sum, not to the per-selection weights.

```python
# routed normalization (unchanged)
normalizer_h = normalizer[perm].view(n_routed_exp, k, 1).to(h.dtype)
h = h * weights / normalizer_h

routed_out = torch.zeros_like(x_flat)
routed_out.index_add_(0, perm, h)

# denominator that includes the always-on shared expert
denom_total = (normalizer + 1.0).unsqueeze(-1).to(shared_out.dtype)
# optional hard floor to avoid amplification:
# denom_total = denom_total.clamp_min(1.0)

out = (shared_out + routed_out) / denom_total
```

### Why your current “+1” did not help

* In eval you do: `(shared + routed) / (counts + 1)`. Good.
* In training you do: `shared / counts + routed/counts` (effectively), because the shared branch is divided by `counts` that **exclude** the shared expert. There is no “+1” in that denominator, so for some tokens `counts≈0` and the shared term explodes.

### Small guardrails that also help

* Ensure `k ≥ 1`:

  ```python
  raw = (n_tokens * (G - 1)) / (G * E)
  k = max(1, int(math.ceil(raw)))
  k = min(k, n_tokens)
  ```
* Log the worst cases to confirm the fix:

  ```python
  with torch.no_grad():
      z = (normalizer == 0)
      if z.any():
          print("zero-routed tokens:", int(z.sum()))
  ```
* If you train in fp16/bf16, add gradient clipping (e.g., 1.0) and check for inf/nan after the MoE block.

If you paste the `forward_topk` block from `shared.py`, I can return an exact patch diff matching your variable names.

---

Below are **drop-in** PyTorch functions for a shared-expert MoE that uses **top-k tokens per routed expert** during training. They implement the two safe normalization choices we discussed:

* `"none"` — do **not** divide the shared branch (simple and stable).
* `"shared_in_denom"` — average the **(shared + routed)** sum by adding `+1` to the per-token denominator (mirrors your eval rule).

They also guard against `k = 0`, empty selections, and tiny denominators.

---

### Code: `compute_normalizers` and `moe_topk_forward`

```python
import math
from typing import List, Literal, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


@torch.no_grad()
def _safe_k(n_tokens: int, G: int, E: int) -> int:
    """
    Compute a safe per-expert capacity (top-k tokens per routed expert).
    Ensures k >= 1 and k <= n_tokens.
    """
    raw = (n_tokens * (G - 1)) / (G * E)
    k = max(1, int(math.ceil(raw)))
    return min(k, n_tokens)


def compute_normalizers(
    n_tokens: int,
    selected_token_idx: torch.Tensor,   # shape [S], each entry in [0, n_tokens)
    selected_weights: torch.Tensor,     # shape [S], same order as selected_token_idx
    eps: float = 1e-6,
    final_scale: Literal["none", "shared_in_denom"] = "none",
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Build per-token denominators for routed and final outputs.

    Args:
        n_tokens: total tokens N = B * T after flattening.
        selected_token_idx: indices of tokens selected by routed experts (length S).
        selected_weights: positive weights per selection (length S), typically
                          taken from a per-token softmax over experts, then
                          gathered for the selections that survived top-k.
        eps: numerical floor.
        final_scale:
            - "none": we will not scale the final sum; denom_final returns ones.
            - "shared_in_denom": denom_final = routed_denom + 1 (shared is always on).

    Returns:
        routed_denom: shape [N], ≥ eps, equals sum of selected_weights per token.
        denom_final: shape [N], ≥ 1.0 for "shared_in_denom", else 1.0.
    """
    device = selected_token_idx.device
    dtype = selected_weights.dtype

    # Sum weights per token: routed_denom[i] = sum_j w_j for token i
    routed_denom = torch.zeros(n_tokens, device=device, dtype=dtype)
    if selected_token_idx.numel() > 0:
        routed_denom.index_add_(0, selected_token_idx, selected_weights)
    # floor to avoid division by zero in routed path
    routed_denom = torch.clamp(routed_denom, min=eps)

    if final_scale == "shared_in_denom":
        # include shared expert in the final averaging
        denom_final = routed_denom + 1.0
        # never amplify the sum: floor at 1.0
        denom_final = torch.clamp(denom_final, min=1.0)
    else:
        # no final scaling
        denom_final = torch.ones(n_tokens, device=device, dtype=dtype)

    return routed_denom, denom_final


def moe_topk_forward(
    x: torch.Tensor,                      # [B, T, D]
    routed_experts: List[nn.Module],      # length E, each maps [*, D] -> [*, D]
    shared_expert: nn.Module,             # maps [N, D] -> [N, D]
    router_logits: torch.Tensor,          # [N, E] before softmax (N=B*T)
    G: int,                               # expert groups, shared counts as +1 in eval
    eps: float = 1e-6,
    final_scale: Literal["none", "shared_in_denom"] = "none",
) -> torch.Tensor:
    """
    Training-time MoE forward (top-k tokens per expert) with a shared expert.

    Selection rule (per routed expert e):
        - Take top-k tokens by the softmax-normalized weight for that expert.
        - Capacity k is derived from (N * (G-1)) / (G * E), but clamped to [1, N].

    Normalization:
        - Routed path: each selected contribution from token i is divided by
          routed_denom[i] = sum of selected routed weights for that token.
        - Shared path:
            - final_scale="none": do not divide the shared branch at all (simple, stable).
            - final_scale="shared_in_denom": average (shared + routed) by (routed_denom + 1).

    Notes:
        - router_logits are softmaxed over E routed experts to get nonnegative weights.
        - Works in bf16/fp16; consider gradient clipping in your training loop.
    """
    assert len(routed_experts) == router_logits.shape[1], "E mismatch between experts and router_logits"

    B, T, D = x.shape
    N = B * T
    E = len(routed_experts)
    x_flat = x.reshape(N, D)

    # Shared branch (always on, no selection)
    shared_out = shared_expert(x_flat)

    # Routed weights: softmax over experts per token (so weights sum to 1 across E)
    # We use these for scoring and for per-token normalization.
    routed_w = F.softmax(router_logits, dim=1)  # [N, E]

    # Capacity per expert
    k = _safe_k(n_tokens=N, G=G, E=E)

    # Collect selections across experts
    # We will build three aligned arrays for the S total selections:
    #   token_idx[S], expert_id[S], sel_w[S]
    token_idx_list = []
    expert_id_list = []
    sel_w_list = []

    # For efficiency, we reuse a range tensor for gather
    arangeN = torch.arange(N, device=x.device)

    for e in range(E):
        w_e = routed_w[:, e]  # [N]
        # Top-k tokens for expert e
        # If N < k, torch.topk will return N elements (safe).
        top_vals, top_idx = torch.topk(w_e, k=k, largest=True, sorted=False)  # each length k
        token_idx_list.append(top_idx)
        expert_id_list.append(torch.full_like(top_idx, fill_value=e))
        sel_w_list.append(top_vals)

    # Concatenate selections from all experts
    token_idx = torch.cat(token_idx_list, dim=0)        # [S] where S = E * k
    expert_id = torch.cat(expert_id_list, dim=0)        # [S]
    sel_w = torch.cat(sel_w_list, dim=0).to(x.dtype)    # [S]

    # Compute denominators
    routed_denom, denom_final = compute_normalizers(
        n_tokens=N,
        selected_token_idx=token_idx,
        selected_weights=sel_w,
        eps=eps,
        final_scale=final_scale,
    )

    # ---- Routed path: evaluate experts on their selected tokens ----
    # We compute expert outputs and scale them by (sel_w / routed_denom[token]).
    routed_out = torch.zeros_like(x_flat)
    if token_idx.numel() > 0:
        # Sort selections by expert to batch expert calls
        # (perm groups by expert to avoid many tiny forward calls)
        perm = torch.argsort(expert_id, stable=True)
        token_idx_sorted = token_idx[perm]
        expert_id_sorted = expert_id[perm]
        sel_w_sorted = sel_w[perm]

        # Segment boundaries per expert
        # positions where expert id changes
        changes = torch.nonzero(expert_id_sorted[1:] != expert_id_sorted[:-1], as_tuple=False).flatten() + 1
        segments = torch.cat([torch.tensor([0], device=x.device), changes, torch.tensor([expert_id_sorted.numel()], device=x.device)])

        # Iterate segments, one per expert
        for s in range(segments.numel() - 1):
            start = int(segments[s].item())
            end = int(segments[s + 1].item())

            e = int(expert_id_sorted[start].item())
            idx_e = token_idx_sorted[start:end]      # [m]
            w_e = sel_w_sorted[start:end]            # [m]
            if idx_e.numel() == 0:
                continue

            x_e = x_flat.index_select(0, idx_e)      # [m, D]
            y_e = routed_experts[e](x_e)             # [m, D]

            denom_e = routed_denom.index_select(0, idx_e)  # [m]
            scale = (w_e / denom_e).unsqueeze(-1).to(x.dtype)  # [m, 1]
            contrib = y_e * scale                      # [m, D]

            # Scatter-add back to token positions
            routed_out.index_add_(0, idx_e, contrib)

    # ---- Combine shared and routed branches ----
    if final_scale == "none":
        out_flat = shared_out + routed_out
    else:  # "shared_in_denom"
        out_flat = (shared_out + routed_out) / denom_final.unsqueeze(-1).to(shared_out.dtype)

    return out_flat.reshape(B, T, D)
```

---

## How this avoids NaNs (and why your dense MLP “just worked”)

**What goes wrong without these fixes.**
During training you were dividing the **shared branch** by a per-token denominator built **only** from routed selections. For tokens that received few or zero routed picks, that denominator is tiny. Dividing the shared output by a tiny number amplifies it by a large factor. In a few layers this overflows the residual stream and gradients become `NaN`. Your dense MLP has no such data-dependent division, so its scale stays controlled by initialization, layer normalization, and optimizer settings.

**Two stable choices for the shared branch.**

1. `final_scale="none"`
   You **do not** divide the shared output at all. You still normalize the **routed** contributions by the routed sum per token:
   [
   y_{\text{routed}}(i) ;=; \sum_{j \in \mathcal{S}(i)} \frac{w_j}{\sum_{k\in \mathcal{S}(i)} w_k}, f_{e(j)}(x_i).
   ]
   The shared contribution ( f_{\text{shared}}(x_i) ) is added without any extra scale. No division by a near-zero term can occur on the shared path.

2. `final_scale="shared_in_denom"`
   If you want the **final** output to be an average over ((\text{shared} + \text{routed})), you add **+1** to the routed denominator **only at the final merge**:
   [
   y(i) ;=; \frac{f_{\text{shared}}(x_i) ;+; \sum_{j \in \mathcal{S}(i)} \frac{w_j}{\sum_{k\in \mathcal{S}(i)} w_k}, f_{e(j)}(x_i)}{\big(\sum_{k\in \mathcal{S}(i)} w_k\big) ;+; 1}.
   ]
   This mirrors your eval rule `(shared + routed) / (counts + 1)` and guarantees the denominator is at least 1.0, so the shared path is never amplified.

**Why not add “+1” earlier?**
If you add `+1` into the **routed** per-selection divisor, you would bias routed scaling and harm equivalence with the eval formula. The stable and consistent place for `+1` is the **final** denominator only.

---

## Top-k selection is per expert, not per token

There are two common MoE selection schemes:

* **Per-token top-k experts** (Switch/Top-2).
* **Per-expert top-k tokens** (capacity framing).

Your earlier code and the `k ≈ N·(G−1)/(G·E)` formula are consistent with **per-expert** selection. The function above therefore:

1. Softmaxes router logits per token to get nonnegative weights over experts.
2. For each expert (e), picks the **top-k tokens** by that expert’s weight.
3. Computes the routed denominator **per token** by summing the selected routed weights for that token.
4. Divides each routed contribution by that per-token routed sum to keep the routed branch scale invariant.
5. Handles the shared branch according to `final_scale`.

This ensures bounded scale even when some tokens get **zero** routed selections (the routed denominator is floored at `eps`, and the final denominator is at least 1.0 in `"shared_in_denom"` mode).

---

## Numerical and training notes

1. **Safety floors.**

   * `routed_denom ≥ eps` prevents division by zero in the routed path.
   * `denom_final ≥ 1.0` in `"shared_in_denom"` prevents shared amplification.

2. **Capacity `k`.**
   Small microbatches can make the original expression yield `k = 0`. `_safe_k` avoids that and clamps `k` to `[1, N]`. Empty expert segments are handled.

3. **Mixed precision.**
   The code works in bf16/fp16. Still, use gradient clipping (e.g., `clip_grad_norm_(..., 1.0)`) in your training loop. Check for `inf/nan` after the block if you are debugging.

4. **Router logits vs weights.**
   The code softmaxes `router_logits` across experts to form weights that sum to 1 per token. You may substitute your own nonnegative weights if you have a different routing rule; the normalizers will still be correct.

5. **Complexity.**
   Per-expert `topk` costs (E \cdot O(N \log k)). The expert forwards run only on selected tokens, which is the point of capacity control.

6. **Eval parity.**
   If your eval path uses `(shared + routed) / (counts + 1)`, pick `final_scale="shared_in_denom"` for training to match that scale. If eval simply sums shared and routed, use `"none"`.

---

## Minimal usage sketch

```python
# x: [B, T, D]
# routed_experts: list of E feed-forward blocks
# shared_expert: one feed-forward block
# router_logits: [B*T, E]

y = moe_topk_forward(
    x=x,
    routed_experts=routed_experts,
    shared_expert=shared_expert,
    router_logits=router_logits,
    G=G,                        # your number of groups
    eps=1e-6,
    final_scale="shared_in_denom"  # or "none"
)
```

If you want me to align names exactly to your `shared.py` (e.g., `permutation_indices`, `normalizer_h`, etc.), paste the surrounding function signature and I will return a patch that fits your file one-to-one.
