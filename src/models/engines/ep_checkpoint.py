"""Expert-parallel checkpoint mapping helpers."""


def _parse_local_expert_key(name: str, local_experts: int):
    """Parse `<prefix>.expert_weight{1|2}.<local_idx>` key format."""
    try:
        base, idx_str = name.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError(f"Malformed expert key (missing suffix): {name}") from exc

    try:
        _, weight_name = base.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError(f"Malformed expert key (missing weight name): {name}") from exc

    if weight_name not in {"expert_weight1", "expert_weight2"}:
        raise ValueError(f"Unsupported expert key prefix: {name}")

    try:
        local_idx = int(idx_str)
    except ValueError as exc:
        raise ValueError(f"Malformed expert key (non-integer index): {name}") from exc

    if local_idx < 0 or local_idx >= local_experts:
        raise ValueError(
            f"Local expert index out of range in key '{name}' "
            f"(local_idx={local_idx}, local_experts={local_experts})"
        )

    return base, local_idx


def _parse_global_expert_key(name: str):
    """Parse `<prefix>.expert_weight{1|2}.<global_idx>` key format."""
    try:
        base, idx_str = name.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError(f"Malformed expert key (missing suffix): {name}") from exc

    try:
        layer_prefix, weight_name = base.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError(f"Malformed expert key (missing weight name): {name}") from exc

    if weight_name not in {"expert_weight1", "expert_weight2"}:
        raise ValueError(f"Unsupported expert key prefix: {name}")

    try:
        global_idx = int(idx_str)
    except ValueError as exc:
        raise ValueError(f"Malformed expert key (non-integer index): {name}") from exc

    if global_idx < 0:
        raise ValueError(f"Malformed expert key (negative index): {name}")

    return layer_prefix, weight_name, global_idx


def compute_local_experts(model_cfg, world_size: int) -> int:
    """Compute local expert count per rank for EP checkpoints."""
    model_type = model_cfg.get("model_type", "")
    shared_expert = bool(model_cfg.get("shared_expert", False))

    n_experts = model_cfg.get("n_experts")
    if n_experts is None:
        granularity = model_cfg.get("granularity")
        expansion = model_cfg.get("expansion")
        if granularity is None or expansion is None:
            raise ValueError("Missing granularity/expansion for EP checkpoint save")
        n_experts = int(granularity) * int(expansion)
        if model_type in {"expert_threshold", "token_choice"} and shared_expert:
            n_experts += 1
    else:
        n_experts = int(n_experts)

    n_routed_experts = (
        n_experts - 1
        if (model_type in {"expert_threshold", "token_choice"} and shared_expert)
        else n_experts
    )

    if n_routed_experts % world_size != 0:
        raise ValueError(
            f"n_routed_experts ({n_routed_experts}) must be divisible by world_size ({world_size}) for EP"
        )

    return n_routed_experts // world_size


def extract_local_expert_state(model):
    """Return local expert-weight params on CPU for object gather."""
    return {
        name: param.data.cpu()
        for name, param in model.named_parameters()
        if "expert_weight" in name
    }


def merge_expert_states(base_state, gathered, local_experts: int, world_size: int):
    """Build full expert-key state dict from gathered local shards."""
    model_state = dict(base_state)

    for key in [k for k in model_state.keys() if "expert_weight" in k]:
        del model_state[key]

    merged_expert_state = {}
    for rank in range(world_size):
        shard = gathered[rank]
        if not isinstance(shard, dict):
            raise ValueError(f"Invalid gathered expert state for rank {rank}: {type(shard)}")

        for name, tensor in shard.items():
            base, local_idx = _parse_local_expert_key(name, local_experts)
            global_idx = rank * local_experts + local_idx
            full_name = f"{base}.{global_idx}"
            if full_name in merged_expert_state:
                raise ValueError(f"Duplicate merged expert key detected: {full_name}")
            merged_expert_state[full_name] = tensor

    for key in sorted(merged_expert_state.keys()):
        model_state[key] = merged_expert_state[key]

    return model_state


def shard_state_for_rank(state_dict, model_cfg, rank: int, world_size: int):
    """Shard full expert-key state dict to local EP key space for one rank."""
    local_experts = compute_local_experts(model_cfg, world_size)
    start = rank * local_experts
    end = start + local_experts

    sharded = {}
    for key, value in state_dict.items():
        if ".expert_weight" in key:
            layer_prefix, weight_name, global_idx = _parse_global_expert_key(key)
            if start <= global_idx < end:
                local_idx = global_idx - start
                local_key = f"{layer_prefix}.{weight_name}.{local_idx}"
                if local_key in sharded:
                    raise ValueError(f"Duplicate sharded expert key detected: {local_key}")
                sharded[local_key] = value
            continue
        sharded[key] = value

    return sharded
