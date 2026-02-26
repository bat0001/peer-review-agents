# Expert-Parallel GEC Brainstorm

## Prompt & Context
- Goal: explore how to extend the existing GEC shared-expert MLP (`src/models/gec_shared/shared.py`) with expert parallelism (EP) where each GPU hosts a subset of experts **and** owns the corresponding optimizer shards.
- Constraints: no code changes yet; think through potential conflicts with the custom ZeRO-like optimizers in `nanochat/nanochat/adamw.py` and `nanochat/nanochat/muon.py`.
- Twist: shared experts must remain data parallel (DP) even if routed experts go EP. Top-k routing and token dispatch require communication-aware design.

## Existing Building Blocks
- `DistAdamW` / `DistMuon` already implement ZeRO-2 style reduce-scatter for gradients and all-gather for parameters, but they assume **full world participation** and row-shard the first tensor dimension (e.g., `grad.shape[0] // world_size`). They also call `dist.get_world_size()` directly in the hot path.
- `GECSharedMLP` expects all experts to live locally. Routing selects indices, gathers/gems locally, and scatters back using `index_add_`.
- No current abstraction for grouping ranks into DP × EP topologies; default assumption is pure DP/ZeRO.

## High-Level EP Strategy
1. **Process topology**  
   - Partition `world_size = dp_size * ep_size`.  
   - Create `dp_group` (same expert layout, different data) and `ep_group` (different experts, same data slice).  
   - Shared expert params live replicated within each DP group (so ZeRO/all-reduce across `dp_group`).  
   - Routed experts get sharded across EP group ranks; each rank hosts `n_local_experts = ceil(n_total_experts / ep_size)`.

2. **Routing on DP ranks**  
   - Router logits computed locally per DP rank (each rank sees its data minibatch).  
   - Produce expert assignments keyed by **global expert ids** → `(expert_id, token_idx, score)`.  
   - Map `expert_id` to owning EP rank via `owner_rank = expert_id // n_local_experts`.

3. **Token dispatch**  
   - Build per-destination buckets (token features + metadata).  
   - Use `all_to_all` inside each EP group to move tokens to the owning expert ranks.  
   - Optionally pre-sort to minimize padding; maintain packed buffers + `split_sizes`.

4. **Per-expert compute**  
   - Each EP rank processes only its resident experts (with local weights).  
   - Local normalizer uses per-token fan-in counts received with metadata.  
   - Outputs packed in the same order as received.

5. **Combine**
   - `all_to_all` to combine expert outputs back to the original token owners (still within EP group).  
   - Original rank scales by router weights / normalizer and accumulates via `index_add_` analog.  
   - Shared expert output (computed locally) added after DP-scope normalization.

## Interaction with Distributed Optimizers
- **Key tension**: existing optimizers assume all params are row-sharded across *world_size*. EP requires:  
  - Shared expert params should reduce across **DP group only**.  
  - Routed expert params should **not** be ZeRO-sharded; each reside fully on a single EP rank (optimizer state local).  
  - Optional: apply ZeRO-2 *within* EP group for very large experts, but then gradients are reduced only across ranks that co-own the expert.

- **Adaptations for `DistAdamW` / `DistMuon`:**
  1. Accept an explicit `process_group`. Replace global `dist.get_world_size()` with `dist.get_world_size(group)`.  
  2. Respect parameter ownership: only shard parameters passed to the optimizer. We can instantiate two optimizers:  
     - `shared_optimizer = DistAdamW(shared_params, group=dp_group)`  
     - `expert_optimizer = torch.optim.AdamW(local_expert_params)` (intra-rank) or reuse `DistAdamW` with `process_group=ep_group` if we opt into ZeRO inside the EP group.  
  3. For EP, ensure `reduce_scatter` / `all_gather` only run within the group that actually shards the tensor. If params are wholly local, skip communicator ops.

- **FSDP / ZeRO interplay**  
  - FSDP stage-1/2 over the shared expert + non-MoE layers is compatible: wrap those modules with `FullyShardedDataParallel(..., process_group=dp_group)`.  
  - Experts should be excluded from FSDP wrapping; their parameters stay local to owning EP ranks.  
  - Trainer must orchestrate multiple sharding strategies: FSDP handles dense layers; EP handles experts; DP gradient averaging only for shared/global params.

## Trainer / Initialization Sketch
```python
# pseudo
topo = ParallelTopology(world_size)
dp_group, ep_group = topo.make_groups()

model = ExpertParallelGEC(config, topology=topo)
model.shared_expert = FSDP(model.shared_expert, process_group=dp_group)
model.router = FSDP(model.router, process_group=dp_group)
model.local_experts = ExpertShardModule(..., owned_experts=topo.local_expert_ids)

shared_optim = DistAdamW(model.shared_parameters(), lr=..., group=dp_group)
expert_optim = torch.optim.AdamW(model.local_expert_parameters(), lr=...)
```
- Gradient steps:  
  1. Forward: DP batch → local routing → EP dispatch/compute → combine.  
  2. Backward: reverse communication (gradients propagate through the all-to-all pairs).  
  3. Optimizers:  
     - `shared_optim.step()` executes `reduce_scatter/all_gather` inside `dp_group`.  
     - `expert_optim.step()` runs locally (no communication) or inside `ep_group` if we use ZeRO there.

## Detailed Algorithm Notes
### Routing Communication
```python
# pseudo: executed per DP rank
assignments = topk(router_logits_flat.t(), k)  # as today, expert-major
dest_rank = expert_owner(assignments.expert_id)
send_buffers[dest_rank].append(TokenBundle(token_id, hidden, weight))

# pack & exchange
xfer = all_to_all_packed(ep_group, send_buffers)
local_inputs = unpack(xfer)
```
- Keep `token_id` relative to the originating DP rank; store `orig_rank` to route outputs back.
- Normalizer requires fan-out counts: either send counts along or recompute after `all_to_all`.

### Expert Compute Skeleton
```python
# pseudo on EP rank
for expert_id, tokens in local_inputs.by_expert():
    h = expert_mlp(tokens.hidden)
    scaled = (h * tokens.weight) / normalizer_lookup(tokens.global_token_id)
    outputs.append((tokens.orig_rank, tokens.global_token_id, scaled))
```
- Use shared normalization utilities from `RouterMixin` by exposing a helper to compute `normalizer` before dispatch and redistributing the relevant slices.

### Combine Phase
```python
# pseudo
combine_outputs = bucket_by_rank(outputs)
responses = all_to_all_packed(ep_group, combine_outputs)
for resp in responses:
    routed_output.index_add_(0, resp.token_id, resp.hidden)
```
- `responses` only target the original DP ranks, so they can update their local buffers.

## Shared Expert (DP) Handling
- Compute shared expert output locally → requires standard DP all-reduce on gradients. FSDP or `DistAdamW` with `dp_group` gives that automatically.
- Ensure normalization factor includes shared expert contribution (currently +1.0). Router statistics remain DP-local but we can `all_reduce` diagnostics if needed.

## Potential Pitfalls & Checks
- **Padding & shape alignment**: `all_to_all` requires equal total volume; using `all_to_all_single` with `split_sizes` avoids heavy padding.  
- **Autograd support**: `all_to_all` is differentiable; ensure metadata tensors (`token_ids`) stay on CPU or detached to avoid gradient tracking.  
- **Overlap with ZeRO**: don’t let `DistAdamW` think it owns params that are not sharded. Pass only the subsets relevant to its group.  
- **Shared experts on DP**: verify gradients flow correctly through normalizer additions; gating weights must broadcast to shared branch without cross-rank dependencies.  
- **Load balancing**: existing top-k ensures fixed tokens per expert; still need to watch stragglers if expert shards are imbalanced.  
- **Mixed precision**: ensure packing/unpacking preserves BF16 dtype; convert metadata to INT32 before communication.

## Suggested Implementation Steps
1. **Topology utils**: helper to build DP/EP groups + expert ownership mapping.  
2. **ExpertParallel dispatcher**: new module alongside `shared.py` (e.g., `src/models/gec_shared/expert_parallel.py`) using the communication pattern above.  
3. **RouterMixin helpers**: expose normalization computation that takes precomputed fan-out and supports distributed contexts.  
4. **Optimizer refactor**: allow `DistAdamW` / `DistMuon` to receive `process_group` and handle non-sharded params gracefully.  
5. **Trainer wiring**: update training loop to initialize groups, wrap shared modules with FSDP, and create two optimizers (shared vs experts).  
6. **Testing scaffolding**:  
   - unit tests that simulate 2×2 DP×EP with fake communication (maybe using `torch.distributed`’s `init_process_group` + `gloo`).  
   - integration test comparing EP vs local execution for small batches.  
   - stress tests on routing overlap + shared expert synchronization.

## Open Questions
- Do we need ZeRO inside EP groups for massive experts? If so, we must adapt reduce-scatter logic to operate on **per-expert shards**, not row-wise across an unrelated tensor order.  
- How to coordinate optimizer state checkpoints when some states are DP-reduced (shared) and others are rank-local (experts)? Likely store per-group shards with metadata (expert → rank).  
- Routing jitter / EMA cutoffs: should those buffers be aggregated across DP group to keep decisions consistent? Possibly average EMAs via `dist.all_reduce`.

## Implementation Sketch for `src/models/gec_shared/shared.py`
```python
# pseudo-implementation only; do not paste into repo verbatim
class GECSharedExpertParallel(GECSharedMLP):
    def __init__(self, config: ModelConfig, topology: ParallelTopology):
        super().__init__(config)
        self.topology = topology
        self.dp_group = topology.dp_group
        self.ep_group = topology.ep_group
        self.ep_size = dist.get_world_size(self.ep_group)
        self.local_expert_ids = topology.local_expert_ids()
        # prune routed expert parameters down to local experts
        self.weight1 = nn.Parameter(self.weight1[self.local_expert_ids].contiguous())
        self.bias1 = nn.Parameter(self.bias1[self.local_expert_ids].contiguous())
        self.weight2 = nn.Parameter(self.weight2[self.local_expert_ids].contiguous())
        self.bias2 = nn.Parameter(self.bias2[self.local_expert_ids].contiguous())

    def forward(self, x: torch.Tensor, layer_idx: int = 0):
        shared_out = self._shared_expert_forward(x.view(-1, x.size(-1)))
        router_logits, routing_ctx = self._distributed_router(x)
        # dispatch tokens (custom autograd)
        expert_inputs, dispatch_ctx = AllToAllTokenDispatch.apply(
            x, router_logits, routing_ctx, self.topology
        )
        expert_outputs = self._local_expert_forward(expert_inputs)
        routed = AllToAllTokenCombine.apply(
            expert_outputs, dispatch_ctx, self.topology
        )
        routed = routed.view_as(x)
        shared = shared_out.view_as(x) / routing_ctx.normalizer.view_as(x[..., :1])
        out = shared + routed
        return out, routing_ctx.metrics
```
- `_distributed_router` sends each rank’s router logits to the owning expert rank **before** the top-k since tokens differ across ranks. Outline:
  1. Compute logits locally → `(B, T, n_experts_local)`.
  2. `all_to_all_single` within `dp_group` to exchange logits needed by each expert owner; buffer layout matches topology mapping.
  3. Perform top-k per expert using combined logits; record owner rank, token ids, and weights in `routing_ctx`.

- `_local_expert_forward` mirrors existing batched GEMMs but uses only the local experts. It consumes packed token buffers plus per-token weights.

## Custom Autograd for Communications
```python
class AllToAllTokenDispatch(torch.autograd.Function):
    @staticmethod
    def forward(ctx, tokens, router_logits, routing_ctx, topo):
        send_buffers, send_splits = pack_tokens(tokens, routing_ctx)
        recv_buffer = torch.empty(sum(routing_ctx.recv_splits) * tokens.size(-1),
                                  device=tokens.device, dtype=tokens.dtype)
        torch.distributed.all_to_all_single(
            recv_buffer, send_buffers,
            recv_splits=routing_ctx.recv_splits,
            send_splits=send_splits,
            group=topo.ep_group,
        )
        ctx.topo = topo
        ctx.routing_ctx = routing_ctx
        ctx.save_for_backward(router_logits)
        return recv_buffer.view(-1, tokens.size(-1))

    @staticmethod
    def backward(ctx, grad_output):
        (router_logits,) = ctx.saved_tensors
        send_grad, send_splits = pack_gradients(grad_output, ctx.routing_ctx)
        recv_grad = torch.empty_like(router_logits)
        torch.distributed.all_to_all_single(
            recv_grad, send_grad,
            recv_splits=ctx.routing_ctx.router_recv_splits,
            send_splits=send_splits,
            group=ctx.topo.ep_group,
        )
        # gradient w.r.t. tokens flows via recv_grad; logits grad handled separately
        token_grad = unpack_token_grad(recv_grad, ctx.routing_ctx)
        logits_grad = compute_router_grad(router_logits, ctx.routing_ctx)
        return token_grad, logits_grad, None, None
```
- `AllToAllTokenCombine` mirrors the dispatch class but runs the inverse permutation in backward.
- Each autograd function stores split sizes, permutations, and fan-out counts so backward can reconstruct gradients without re-running the router.
- Gradients for router logits originate from the softmax/activation used in `_distributed_router`. Combine them with the returned `logits_grad`.

## Router Logit Communication
- Because DP ranks own disjoint token batches, a single rank lacks the logits for experts it does not host. The plan:
  1. Compute local logits.  
  2. Build `send_splits` mapping token ownership → expert owner.  
  3. Perform an `all_to_all_single` (within `dp_group`) to gather the logits required for each expert’s top-k selection.  
  4. Execute top-k on the receiver rank; produce `(token_idx, routed_weights, fanout_counts)` arrays and broadcast them back via `all_to_all_single`.  
- This yields exactly **one communication** for router logits per forward pass, minimizing redundant data movement while maintaining consistent routing decisions across DP replicas.

### Overlapping Communication with Shared Expert Compute
```python
with torch.cuda.stream(self.comm_stream):
    comm_work = dist.all_to_all_single(
        logits_recv, logits_send,
        recv_splits=routing_ctx.logit_recv_splits,
        send_splits=routing_ctx.logit_send_splits,
        group=self.dp_group,
        async_op=True,
    )

with torch.cuda.stream(self.compute_stream):
    shared_flat = self._shared_expert_forward(x_flat)  # runs while comm in flight

torch.cuda.current_stream().wait_stream(self.compute_stream)
comm_work.wait()  # ensure router logits ready before expert routing
```
- Use dedicated CUDA streams (`comm_stream`, `compute_stream`) created at module init (`torch.cuda.Stream()`). The async handle enables CUDA/NCCL overlap; shared expert matmuls proceed on `compute_stream` while the NCCL transfer occurs on `comm_stream`. Synchronize once both results are needed (prior to routing decisions and final accumulation).
