# Plan: Align aux loss with router activation in ScatterMoE token-choice

## Context
`src/models/scattermoe_tc.py` computes aux load-balancing loss with a softmax over
raw logits, while gating weights for the forward pass come from
`apply_router_activation` (sigmoid/relu/softmax_e). That makes aux gradients
mismatch the actual gate behavior for non-softmax activations.

## Recommendation
Use `all_weights` (activated weights for all experts, pre-top-k) to compute the
aux loss probability term `p`. Keep `f` as the selection mask over top-k choices.
This preserves the Switch/GShard structure while aligning aux to the actual
router activation used for gating.

## Why not use `gates` (top-k only)?
Using `gates` would make `p` depend on top-k selection, which is already encoded
in `f`, and would remove gradient signal for unselected experts. `all_weights`
keeps `p` defined over *all* experts and maintains a balancing gradient even for
experts that are currently not being selected.

## Edit plan
1. Update aux loss computation in `ScatterMoETokenChoiceMLP.forward` to use
   `all_weights.mean(dim=0)` instead of `softmax(router_logits_flat)`.
2. Update aux loss computation in `ScatterMoETokenChoiceSharedMLP.forward` the
   same way.
3. (Optional) Update `memory/design/token_choice_moe.md` to state that `p` uses
   activated weights (not raw-logit softmax), keeping the documented formula
   in sync with code.

## Code snippet (proposed change)

In `src/models/scattermoe_tc.py` (both classes):

```python
if self.load_balance_method == "aux":
    # Use activated weights for all experts to align with gating.
    router_weights = all_weights
    mask = torch.zeros_like(router_weights)
    mask.scatter_(1, expert_idxs, 1.0 / float(top_k))
    f = mask.mean(dim=0)
    p = router_weights.mean(dim=0)
    metrics["aux_loss"] = n_experts * torch.sum(f * p)
```

For `tc_shared`, replace `n_experts` with `n_routed_experts` as already done.

## Validation
- No new tests required; existing CUDA smoke test should still pass.
- If you want a sanity check, log `aux_loss` and ensure it changes smoothly
  when toggling `router_activation` between `sigmoid` and `relu`.
