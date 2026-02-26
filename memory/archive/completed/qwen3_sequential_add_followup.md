# Implementation Plan: Qwen3 Sequential-Add Forward Path

Implementation order: **(1) Triton kernel → (2) Autograd op wrapper → (3) Torch inverse-index utilities → (4) Benchmark hook (forward only) → (5) Unit tests → (6) New GEC module overriding `forward_topk`.** Backward will be handled later (simple gather).

---

## 1. Triton Kernel (`src/kernels/gec_sequential_add.py`)

- Define forward-only Triton kernel that consumes token-major metadata and performs fused weight accumulation.
- Draft kernel:

```python
@triton.jit
def gec_sequential_add_kernel(
    expert_out_ptr,
    weight_ptr,
    sorted_expert_ptr,
    sorted_local_ptr,
    token_start_ptr,
    out_ptr,
    stride_expert,
    stride_capacity,
    hidden_size: tl.constexpr,
    max_fanout: tl.constexpr,
    BLOCK_HID: tl.constexpr,
):
    token_id = tl.program_id(0)
    hid_offsets = tl.arange(0, BLOCK_HID)
    mask_h = hid_offsets < hidden_size

    start = tl.load(token_start_ptr + token_id)
    end = tl.load(token_start_ptr + token_id + 1)
    count = end - start

    acc = tl.zeros([BLOCK_HID], dtype=tl.float32)

    for slot in range(max_fanout):
        process = slot < count
        if not tl.any(process):
            break
        idx = start + slot
        expert = tl.load(sorted_expert_ptr + idx, mask=process, other=0)
        local = tl.load(sorted_local_ptr + idx, mask=process, other=0)

        base = expert * stride_expert + local * stride_capacity
        ptr = expert_out_ptr + base + hid_offsets
        val = tl.load(ptr, mask=mask_h, other=0.0)

        if weight_ptr is not None:
            w = tl.load(weight_ptr + idx, mask=process, other=0.0)
            val = val * w

        acc += val.to(tl.float32)

    tl.store(out_ptr + token_id * stride_capacity + hid_offsets, acc, mask=mask_h)
```

- Strides follow `[num_experts, capacity, hidden_size]` layout; pass `stride_capacity = hidden_size`.
- Launch helper:

```python
def launch_gec_sequential_add(expert_out, weights, sorted_expert, sorted_local, token_start, max_fanout):
    num_tokens = token_start.numel() - 1
    hidden = expert_out.size(-1)
    block = min(128, triton.next_power_of_2(hidden))
    grid = (num_tokens,)
    kernels.gec_sequential_add_kernel[grid](
        expert_out, weights, sorted_expert, sorted_local, token_start,
        out, stride_expert=expert_out.stride(0) * expert_out.element_size(),
        stride_capacity=expert_out.stride(1) * expert_out.element_size(),
        hidden_size=hidden, max_fanout=max_fanout, BLOCK_HID=block,
    )
    return out
```

- Ensure accumulation uses float32 even when inputs are bf16/fp16.
- Validate `max_fanout` passed from metadata (compute once from `token_start`).
- Follow `balanced.py` weight fusion pattern (load weights, multiply before accumulation).

---

## 2. Autograd Wrapper (`src/ops/gec_sequential_add.py`)

- Implement `SequentialAddOp(torch.autograd.Function)` similar to `ScatterOp`.
- Forward:

```python
class SequentialAddOp(torch.autograd.Function):
    @staticmethod
    @custom_fwd(device_type="cuda")
    def forward(ctx, expert_out, sorted_expert, sorted_local, token_start, max_fanout, weights=None):
        assert expert_out.is_cuda and sorted_expert.is_cuda
        out = torch.zeros(token_start.numel() - 1, expert_out.size(-1), device=expert_out.device, dtype=torch.float32)
        kernels.gec_sequential_add(
            out,
            expert_out,
            sorted_expert.int(),
            sorted_local.int(),
            token_start.int(),
            weights.float() if weights is not None else None,
            max_fanout=max_fanout,
        )
        ctx.save_for_backward(sorted_expert, sorted_local, token_start, weights)
        ctx.expert_shape = expert_out.shape
        ctx.has_weights = weights is not None
        return out.to(expert_out.dtype)

    @staticmethod
    @custom_bwd(device_type="cuda")
    def backward(ctx, grad_out):
        raise NotImplementedError("Backward for sequential add will use simple gather in follow-up.")
```

- Export `sequential_add = SequentialAddOp.apply` in `src/ops/__init__.py`.
- No torch fallback—forward always expects Triton path; tests guard against missing Triton.

---

## 3. Inverse Index Utilities (`src/utils/gec_inverse.py`)

- Provide torch-only helpers to derive token-major metadata from expert-major sorted indices.
- Use tensor ops (no Python loops) with explicit global ordering step:

```python
def build_inverse_indices(indices, weights=None, num_tokens=None):
    # indices: [num_experts, capacity], each row sorted ascending
    device = indices.device
    num_experts, capacity = indices.shape
    flat_token = indices.reshape(-1)  # (num_experts * capacity,)
    expert_id = torch.arange(num_experts, device=device).repeat_interleave(capacity)
    local_idx = torch.arange(capacity, device=device).repeat(num_experts)

    order = torch.argsort(flat_token)  # merge per-expert sorted lists into token-major order
    sorted_token = flat_token.index_select(0, order)
    sorted_expert = expert_id.index_select(0, order)
    sorted_local = local_idx.index_select(0, order)
    sorted_weight = weights.reshape(-1).index_select(0, order) if weights is not None else None

    num_tokens = int(num_tokens or (sorted_token[-1].item() + 1))
    token_counts = torch.bincount(sorted_token, minlength=num_tokens)
    token_start = torch.cat([token_counts.new_zeros(1), torch.cumsum(token_counts, dim=0)])

    return {
        "sorted_token": sorted_token,
        "sorted_expert": sorted_expert,
        "sorted_local": sorted_local,
        "token_start": token_start,
        "sorted_weight": sorted_weight,
        "max_fanout": int(token_counts.max().item()),
    }
```

- Provide validation that `indices` rows are sorted (optional debug assert).
- Package helper into namespace `_infer_max_fanout`, `_pack_for_kernel` etc. All torch ops, no CPU loops.

---

## 4. Benchmark Wiring (`benchmark/permutation/scatter/__init__.py`)

- Add new entry `bench_seq_add_gec`.
- Flow:
  1. Reuse existing data prep to build `expert_out`, `indices`, `weights`.
  2. Call `build_inverse_indices` to obtain metadata.
  3. Benchmark wrapper that launches `SequentialAddOp`.
- Example integration:

```python
def bench_seq_add_gec(cfg):
    expert_out, indices, weights = prepare_inputs(cfg)  # already on CUDA
    meta = build_inverse_indices(indices, weights=weights, num_tokens=cfg.num_tokens)

    def run():
        return sequential_add(
            expert_out,
            meta["sorted_expert"],
            meta["sorted_local"],
            meta["token_start"],
            meta["max_fanout"],
            meta["sorted_weight"],
        )

    kernel_ms = triton.testing.do_bench(run)
    return {"kernel_ms": kernel_ms}
```

- Optionally time inverse-index construction separately and surface in benchmark output (for fair comparison).
- Hook new mode into CLI parser and summary table.

---

## 5. Tests

- **Inverse utilities** (`tests/utils/test_gec_inverse.py`):
  - Random routing sets; verify `token_start[t+1]-token_start[t]` matches actual fanout.
  - Ensure sorted outputs reproduce original expert-major structures via inverse mapping.
- **Kernel/op** (`tests/ops/test_gec_sequential_add.py`):
  - Compare `SequentialAddOp` output to reference torch accumulation using `scatter_add_` (forward only).
  - Cover both with and without weights; include max-fanout cases.
  - Skip if Triton unavailable.
- **Integration** (`tests/models/test_gec_seq_add.py`):
  - Smoke test new module `GECSequentialAddMLP` for forward parity on small inputs against reference `GECMLP`.

---

## 6. New GEC Module (`src/models/gec_seq_add.py`)

- Subclass reference implementation and override `forward_topk` only.
- Draft:

```python
class GECSequentialAddMLP(GECMLP):
    def forward_topk(self, x, router_logits, router_weights=None):
        assignments = super().forward_topk_indices(x, router_logits)  # helper to reuse gating
        meta = build_inverse_indices(assignments.indices, weights=router_weights, num_tokens=self.num_tokens)
        expert_out = self.compute_expert_outputs(assignments)
        token_out = sequential_add(
            expert_out,
            meta["sorted_expert"],
            meta["sorted_local"],
            meta["token_start"],
            meta["max_fanout"],
            meta["sorted_weight"],
        )
        return token_out.view_as(x), assignments.metadata
```

- Wire new class into `models/__init__.py` and config flag to select implementation.
- Update `models/README.md` describing sequential-add path (forward only, fused weights).

---

## Notes & Follow-ups

- Backward (simple gather) deferred; leave clear TODO in autograd backward.
- Ensure dtype conversions mirror `src/kernels/balanced.py`.
- After benchmarks, log performance deltas in `memory/benchmarks/speedup.md`.
