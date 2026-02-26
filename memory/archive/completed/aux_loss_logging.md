# Aux Loss Included in Train Loss Logging

## Summary
Training loss logs were reporting the optimization objective (CE + aux) for token-choice
models using `load_balance_method=aux`, which made the loss appear better than CE. Eval
loss was already pure CE, so train/eval were inconsistent.

## Root Cause
`train.py` logs `output.loss`, and `src/models/model_base.py` adds the auxiliary loss
during training whenever `aux_loss_total` is present and `aux_loss_coef > 0`.

## Fix
Keep the numeric value of `loss` equal to CE for logging, while preserving aux gradients
via a detach trick in `src/models/model_base.py`:
```
aux_term = aux_loss_coef * aux_loss_total
loss = loss + aux_term - aux_term.detach()
```
This preserves the optimization objective without changing APIs or logging code.

## Verification
- Run `script/run_tc_shared.sh` with `LOAD_BALANCE=aux` and confirm logged `loss` matches CE.
- Confirm `aux_loss` still logs as a separate metric.
- Non-aux models (GEC/EC/DeepSeek) should be unchanged since they never add aux.
