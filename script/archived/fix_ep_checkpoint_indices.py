#!/usr/bin/env python3
"""Fix EP checkpoint expert index gaps by remapping per-layer expert indices.

This script scans outputs/**/checkpoints/*.pt for runs whose directory name
ends with "_ep" or "_ep<digits>", verifies expert_parallel=True, and rewrites
expert_weight{1,2}.<idx> keys per layer to be contiguous 0..n_routed_experts-1.

Original checkpoints are preserved; fixed checkpoints are saved as *_fixed.pt.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Tuple

import torch


EP_SUFFIX_RE = re.compile(r"_ep\d*$")
EXPERT_KEY_RE = re.compile(r"\.(expert_weight[12])\.(\d+)$")


def _is_ep_run_path(ckpt_path: Path) -> bool:
    # Path: outputs/<run>/<run>/checkpoints/checkpoint_step_*.pt
    run_dir = ckpt_path.parent.parent
    return EP_SUFFIX_RE.search(run_dir.name) is not None


def _get_n_routed_experts(model_cfg: Dict) -> int:
    model_type = model_cfg.get("model_type", "")
    n_experts = model_cfg.get("n_experts")
    if n_experts is None:
        G = model_cfg.get("granularity")
        E = model_cfg.get("expansion")
        if G is None or E is None:
            raise ValueError("Missing granularity/expansion in checkpoint config")
        n_experts = int(G) * int(E)
        if "shared" in model_type:
            n_experts += 1
    if "shared" in model_type:
        return int(n_experts) - 1
    return int(n_experts)


def _build_group_maps(state_dict: Dict[str, torch.Tensor], n_routed_experts: int) -> Dict[Tuple[str, str], Dict[int, int]]:
    # Group by (prefix, weight_type) and compute old->new index maps.
    groups = {}
    for key in state_dict.keys():
        match = EXPERT_KEY_RE.search(key)
        if not match:
            continue
        weight_type = match.group(1)
        idx = int(match.group(2))
        prefix = key[: match.start(1) - 1]  # drop ".expert_weightX"
        group_key = (prefix, weight_type)
        groups.setdefault(group_key, set()).add(idx)

    group_maps = {}
    for group_key, idx_set in groups.items():
        indices = sorted(idx_set)
        if len(indices) != n_routed_experts:
            raise ValueError(
                f"{group_key[0]} {group_key[1]} has {len(indices)} experts, "
                f"expected {n_routed_experts}"
            )
        if indices != list(range(n_routed_experts)):
            group_maps[group_key] = {old_idx: new_idx for new_idx, old_idx in enumerate(indices)}
    return group_maps


def _rewrite_state_dict(state_dict: Dict[str, torch.Tensor], group_maps: Dict[Tuple[str, str], Dict[int, int]]) -> Tuple[Dict[str, torch.Tensor], bool]:
    new_state = {}
    changed = False
    for key, tensor in state_dict.items():
        match = EXPERT_KEY_RE.search(key)
        if not match:
            if key in new_state:
                raise ValueError(f"Duplicate key after rewrite: {key}")
            new_state[key] = tensor
            continue

        weight_type = match.group(1)
        idx = int(match.group(2))
        prefix = key[: match.start(1) - 1]
        group_key = (prefix, weight_type)

        if group_key in group_maps:
            new_idx = group_maps[group_key][idx]
            new_key = f"{prefix}.{weight_type}.{new_idx}"
        else:
            new_key = key

        if new_key != key:
            changed = True
        if new_key in new_state:
            raise ValueError(f"Key collision after rewrite: {new_key}")
        new_state[new_key] = tensor
    return new_state, changed


def fix_checkpoint(path: Path) -> bool:
    checkpoint = torch.load(path, map_location="cpu")
    config = checkpoint.get("config", {})
    model_cfg = config.get("model", {})
    if not model_cfg.get("expert_parallel", False):
        return False

    n_routed_experts = _get_n_routed_experts(model_cfg)
    state_dict = checkpoint.get("model_state_dict")
    if state_dict is None:
        raise ValueError(f"Checkpoint missing model_state_dict: {path}")

    group_maps = _build_group_maps(state_dict, n_routed_experts)
    if not group_maps:
        return False

    new_state, changed = _rewrite_state_dict(state_dict, group_maps)
    if not changed:
        return False

    checkpoint["model_state_dict"] = new_state
    out_path = path.with_name(path.name.replace(".pt", "_fixed.pt"))
    torch.save(checkpoint, out_path)
    print(f"[fixed] {path} -> {out_path}")
    return True


def main() -> None:
    root = Path("outputs")
    if not root.exists():
        raise FileNotFoundError("outputs/ not found; run from repo root")

    paths = sorted(root.rglob("checkpoints/*.pt"))
    if not paths:
        print("No checkpoints found.")
        return

    total = 0
    fixed = 0
    for path in paths:
        if not _is_ep_run_path(path):
            continue
        total += 1
        try:
            if fix_checkpoint(path):
                fixed += 1
        except Exception as exc:
            print(f"[error] {path}: {exc}")

    print(f"EP checkpoints scanned: {total}, fixed: {fixed}")


if __name__ == "__main__":
    main()
