#!/usr/bin/env python3
"""Standalone routing-logit histogram eval on FineWeb val split.

This script mirrors existing eval config usage (Hydra config + checkpoint loading)
and uses the same representative-layer / selected-expert logic as routing metrics:
- Selected layers: {0, 1, n_layer//4, n_layer//2, 3*n_layer//4, n_layer-1}
- Selected experts:
  - E0 for every selected layer
  - Elast additionally for first/last selected layers {0, 1, n_layer-1}
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

import hydra
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from omegaconf import DictConfig, OmegaConf
import torch
import torch.nn.functional as F

from src.config import Config
from src.data_loader import create_data_loader
from src.eval.val_loss import compute_eval_steps
from src.models import BaseGPT, ModelConfig
from src.models.model_base import norm
from src.tokenizer import get_tokenizer
from src.utils.distributed import compute_init, compute_cleanup, print0

HIST_BINS = 100
GLOBAL_TOTAL_FANOUT_MIN_COUNT = 200


@dataclass
class RunningBivariateStats:
    n: int = 0
    sum_x: float = 0.0
    sum_y: float = 0.0
    sum_x2: float = 0.0
    sum_y2: float = 0.0
    sum_xy: float = 0.0

    def update(self, x: torch.Tensor, y: torch.Tensor) -> None:
        if x.numel() == 0:
            return
        if x.shape != y.shape:
            raise ValueError(f"x/y shape mismatch: {tuple(x.shape)} vs {tuple(y.shape)}")
        x = x.to(torch.float64)
        y = y.to(torch.float64)
        self.n += int(x.numel())
        self.sum_x += float(x.sum().item())
        self.sum_y += float(y.sum().item())
        self.sum_x2 += float((x * x).sum().item())
        self.sum_y2 += float((y * y).sum().item())
        self.sum_xy += float((x * y).sum().item())

    def finalize(self) -> dict[str, float | int | None]:
        result: dict[str, float | int | None] = {
            "n_samples": self.n,
            "pearson_r": None,
            "r2": None,
            "slope": None,
        }
        if self.n < 2:
            return result

        n_float = float(self.n)
        mean_x = self.sum_x / n_float
        mean_y = self.sum_y / n_float
        var_x = (self.sum_x2 / n_float) - (mean_x * mean_x)
        var_y = (self.sum_y2 / n_float) - (mean_y * mean_y)
        cov_xy = (self.sum_xy / n_float) - (mean_x * mean_y)

        if var_x <= 0.0 or var_y <= 0.0:
            return result

        slope = cov_xy / var_x
        denom = math.sqrt(var_x * var_y)
        r = cov_xy / denom if denom > 0.0 else 0.0
        r = max(-1.0, min(1.0, r))
        result["pearson_r"] = r
        result["r2"] = r * r
        result["slope"] = slope
        return result


def _selected_layers(n_layer: int) -> list[int]:
    layers = {0, 1, n_layer // 4, n_layer // 2, 3 * n_layer // 4, n_layer - 1}
    return sorted(l for l in layers if 0 <= l < n_layer)


def _selected_experts(layer_idx: int, n_layer: int, n_routed_experts: int) -> list[int]:
    experts = [0]
    first_last_layers = {0, 1, n_layer - 1}
    if layer_idx in first_last_layers and n_routed_experts > 1:
        experts.append(n_routed_experts - 1)
    return experts


def _get_router(mlp):
    if hasattr(mlp, "engine") and hasattr(mlp.engine, "router"):
        return mlp.engine.router
    if hasattr(mlp, "router"):
        return mlp.router
    return None


def _get_cutoff_ema(mlp):
    if hasattr(mlp, "engine") and hasattr(mlp.engine, "cutoff_ema"):
        cutoff = mlp.engine.cutoff_ema
        return cutoff if torch.is_tensor(cutoff) else None
    if hasattr(mlp, "cutoff_ema"):
        cutoff = mlp.cutoff_ema
        return cutoff if torch.is_tensor(cutoff) else None
    return None


def load_checkpoint_model(checkpoint_path: str, device: torch.device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if "config" not in checkpoint:
        raise ValueError("Checkpoint missing config")

    config = Config.from_dict(checkpoint["config"])

    # Force single-GPU analysis path (no EP sharding needed).
    config.model["expert_parallel"] = False

    tokenizer = get_tokenizer(config.data.tokenizer_dir)
    config.model["vocab_size"] = tokenizer.get_vocab_size()

    model_config = ModelConfig(**config.model)
    model = BaseGPT(model_config)

    state_dict = checkpoint["model_state_dict"]
    model_state_keys = set(model.state_dict().keys())
    remapped = {}
    for key, value in state_dict.items():
        new_key = key
        if key.endswith("cutoff_ema") and key[:-len("cutoff_ema")] + "cutoff_ema_raw" in model_state_keys:
            new_key = key[:-len("cutoff_ema")] + "cutoff_ema_raw"
        elif key.endswith("cutoff_ema_raw") and key[:-len("cutoff_ema_raw")] + "cutoff_ema" in model_state_keys:
            new_key = key[:-len("cutoff_ema_raw")] + "cutoff_ema"
        remapped[new_key] = value
    state_dict = remapped

    missing_keys, unexpected_keys = model.load_state_dict(state_dict, strict=False)
    allowed_missing = {k for k in missing_keys if k.endswith("cutoff_ema_updates")}
    if unexpected_keys or (set(missing_keys) - allowed_missing):
        raise RuntimeError(
            "Checkpoint compatibility error. "
            f"missing_keys={missing_keys}, unexpected_keys={unexpected_keys}"
        )
    model.to(device)
    model.eval()

    return model, tokenizer, config


def _tensor_stats(values: torch.Tensor) -> dict:
    percentiles = torch.quantile(
        values,
        torch.tensor([0.01, 0.05, 0.50, 0.95, 0.99], dtype=values.dtype),
    )
    hist = torch.histogram(values, bins=HIST_BINS)
    return {
        "count": int(values.numel()),
        "mean": float(values.mean().item()),
        "std": float(values.std(unbiased=False).item()),
        "min": float(values.min().item()),
        "max": float(values.max().item()),
        "percentiles": {
            "p01": float(percentiles[0].item()),
            "p05": float(percentiles[1].item()),
            "p50": float(percentiles[2].item()),
            "p95": float(percentiles[3].item()),
            "p99": float(percentiles[4].item()),
        },
        "hist_counts": [int(v) for v in hist.hist.tolist()],
        "hist_bin_edges": [float(v) for v in hist.bin_edges.tolist()],
    }


def _plot_histogram(
    values: torch.Tensor,
    title: str,
    output_path: Path,
    cutoff_ema: float | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    plt.hist(values.numpy(), bins=HIST_BINS, color="#CC4E1A", edgecolor="black", alpha=0.85)
    if cutoff_ema is not None:
        plt.axvline(cutoff_ema, color="#1f4aa8", linestyle="--", linewidth=2.0, label="cutoff_ema")
        plt.legend()
    plt.title(title)
    plt.xlabel("Router Logit")
    plt.ylabel("Count")
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def _plot_fanout_vs_position(
    fanout_position_means: dict[int, list[float]],
    global_mean: list[float],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(12, 6))
    positions = list(range(len(global_mean)))

    for layer_idx in sorted(fanout_position_means):
        plt.plot(
            positions,
            fanout_position_means[layer_idx],
            linewidth=1.0,
            alpha=0.25,
            color="#4E79A7",
        )

    plt.plot(
        positions,
        global_mean,
        linewidth=2.5,
        color="#E15759",
        label="Global mean across layers",
    )
    plt.title("Mean Fanout vs Position")
    plt.xlabel("Token Position")
    plt.ylabel("Mean Fanout")
    plt.grid(alpha=0.2)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def _plot_loss_vs_fanout(
    layer_bin_stats: dict[int, dict[int, dict[str, float | int]]],
    highlight_layers: list[int],
    per_layer_fanout_max: int | None,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 6))
    highlight_set = set(highlight_layers)
    highlight_palette = ["#4E79A7", "#E15759", "#59A14F", "#F28E2B", "#B07AA1"]
    highlight_colors = {
        layer_idx: highlight_palette[i % len(highlight_palette)]
        for i, layer_idx in enumerate(sorted(highlight_layers))
    }

    global_bins: dict[int, dict[str, float | int]] = defaultdict(
        lambda: {"count": 0, "sum_loss": 0.0, "sum_sq_loss": 0.0}
    )

    for layer_idx in sorted(layer_bin_stats):
        bins = sorted(layer_bin_stats[layer_idx])
        if not bins:
            continue
        x_vals = []
        y_vals = []
        for fanout_bin in bins:
            stat = layer_bin_stats[layer_idx][fanout_bin]
            count = int(stat["count"])
            if count <= 0:
                continue
            mean_loss = float(stat["sum_loss"]) / count
            x_vals.append(fanout_bin)
            y_vals.append(mean_loss)

            g = global_bins[fanout_bin]
            g["count"] = int(g["count"]) + count
            g["sum_loss"] = float(g["sum_loss"]) + float(stat["sum_loss"])
            g["sum_sq_loss"] = float(g["sum_sq_loss"]) + float(stat["sum_sq_loss"])

        if x_vals:
            if layer_idx in highlight_set:
                plt.plot(
                    x_vals,
                    y_vals,
                    linewidth=1.8,
                    alpha=0.95,
                    color=highlight_colors[layer_idx],
                    label=f"L{layer_idx}",
                )
            else:
                plt.plot(
                    x_vals,
                    y_vals,
                    linewidth=1.0,
                    alpha=0.35,
                    color="#B8B8B8",
                )

    global_x = []
    global_y = []
    for fanout_bin in sorted(global_bins):
        count = int(global_bins[fanout_bin]["count"])
        if count <= 0:
            continue
        global_x.append(fanout_bin)
        global_y.append(float(global_bins[fanout_bin]["sum_loss"]) / count)

    if global_x:
        plt.plot(global_x, global_y, linewidth=2.5, color="#F28E2B", label="Global mean")

    plt.title("Token NLL vs Fanout (Binned)")
    plt.xlabel("Fanout Bin")
    plt.ylabel("Mean Token NLL")
    if per_layer_fanout_max is not None and per_layer_fanout_max > 0:
        plt.xlim(0, per_layer_fanout_max)
    plt.grid(alpha=0.2)
    if global_x:
        plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def _plot_loss_vs_total_fanout(
    global_bin_stats: dict[int, dict[str, float | int]],
    output_path: Path,
    min_count_for_plot: int,
    global_fanout_max: int | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 6))

    x_vals = []
    y_vals = []
    for fanout_bin in sorted(global_bin_stats):
        stat = global_bin_stats[fanout_bin]
        count = int(stat["count"])
        if count < min_count_for_plot:
            continue
        mean_loss = float(stat["sum_loss"]) / count
        x_vals.append(fanout_bin)
        y_vals.append(mean_loss)

    if x_vals:
        plt.plot(x_vals, y_vals, linewidth=2.2, color="#E15759")
    else:
        plt.text(
            0.5,
            0.5,
            f"No bins with count >= {min_count_for_plot}",
            ha="center",
            va="center",
            transform=plt.gca().transAxes,
        )

    plt.title(f"Token NLL vs Total Fanout (count >= {min_count_for_plot})")
    plt.xlabel("Total Fanout Bin (all MoE layers)")
    plt.ylabel("Mean Token NLL")
    if global_fanout_max is not None and global_fanout_max > 0:
        plt.xlim(0, global_fanout_max)
    plt.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def _finalize_loss_bin_stats(
    layer_bin_stats: dict[int, dict[int, dict[str, float | int]]]
) -> dict[str, dict[str, dict[str, float | int]]]:
    finalized: dict[str, dict[str, dict[str, float | int]]] = {}
    for layer_idx in sorted(layer_bin_stats):
        layer_key = f"L{layer_idx}"
        finalized[layer_key] = {}
        for fanout_bin in sorted(layer_bin_stats[layer_idx]):
            stat = layer_bin_stats[layer_idx][fanout_bin]
            count = int(stat["count"])
            if count <= 0:
                continue
            mean_loss = float(stat["sum_loss"]) / count
            variance = (float(stat["sum_sq_loss"]) / count) - (mean_loss * mean_loss)
            variance = max(0.0, variance)
            finalized[layer_key][str(fanout_bin)] = {
                "count": count,
                "mean_loss": mean_loss,
                "std_loss": math.sqrt(variance),
            }
    return finalized


def _write_loss_vs_fanout_csv(
    layer_bin_stats: dict[int, dict[int, dict[str, float | int]]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["layer", "fanout_bin", "count", "mean_loss", "std_loss"])
        for layer_idx in sorted(layer_bin_stats):
            for fanout_bin in sorted(layer_bin_stats[layer_idx]):
                stat = layer_bin_stats[layer_idx][fanout_bin]
                count = int(stat["count"])
                if count <= 0:
                    continue
                mean_loss = float(stat["sum_loss"]) / count
                variance = (float(stat["sum_sq_loss"]) / count) - (mean_loss * mean_loss)
                variance = max(0.0, variance)
                std_loss = math.sqrt(variance)
                writer.writerow([layer_idx, fanout_bin, count, mean_loss, std_loss])


def _finalize_global_loss_bin_stats(
    global_bin_stats: dict[int, dict[str, float | int]],
    min_count_for_plot: int,
) -> dict[str, dict[str, float | int | bool]]:
    finalized: dict[str, dict[str, float | int | bool]] = {}
    for fanout_bin in sorted(global_bin_stats):
        stat = global_bin_stats[fanout_bin]
        count = int(stat["count"])
        if count <= 0:
            continue
        mean_loss = float(stat["sum_loss"]) / count
        variance = (float(stat["sum_sq_loss"]) / count) - (mean_loss * mean_loss)
        variance = max(0.0, variance)
        finalized[str(fanout_bin)] = {
            "count": count,
            "mean_loss": mean_loss,
            "std_loss": math.sqrt(variance),
            "included_in_plot": count >= min_count_for_plot,
        }
    return finalized


def _write_loss_vs_total_fanout_csv(
    global_bin_stats: dict[int, dict[str, float | int]],
    output_path: Path,
    min_count_for_plot: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["fanout_bin", "count", "mean_loss", "std_loss", "included_in_plot"])
        for fanout_bin in sorted(global_bin_stats):
            stat = global_bin_stats[fanout_bin]
            count = int(stat["count"])
            if count <= 0:
                continue
            mean_loss = float(stat["sum_loss"]) / count
            variance = (float(stat["sum_sq_loss"]) / count) - (mean_loss * mean_loss)
            variance = max(0.0, variance)
            std_loss = math.sqrt(variance)
            writer.writerow([fanout_bin, count, mean_loss, std_loss, count >= min_count_for_plot])


def _write_fanout_vs_position_csv(
    fanout_position_sum: dict[int, torch.Tensor],
    fanout_position_count: dict[int, torch.Tensor],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["layer", "position", "count", "mean_fanout"])
        for layer_idx in sorted(fanout_position_sum):
            sums = fanout_position_sum[layer_idx]
            counts = fanout_position_count[layer_idx]
            for pos in range(len(sums)):
                count = int(counts[pos].item())
                if count <= 0:
                    continue
                mean_val = float(sums[pos].item()) / count
                writer.writerow([layer_idx, pos, count, mean_val])


def _write_fanout_vs_position_global_csv(
    global_mean: list[float],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["position", "mean_fanout_global"])
        for pos, value in enumerate(global_mean):
            writer.writerow([pos, value])


def _write_correlation_csv(
    per_layer: dict[int, dict[str, float | int | None]],
    total_fanout: dict[str, float | int | None],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["scope", "layer", "n_samples", "pearson_r", "r2", "slope"])
        for layer_idx in sorted(per_layer):
            stats = per_layer[layer_idx]
            writer.writerow(
                [
                    "layer",
                    layer_idx,
                    int(stats["n_samples"]),
                    stats["pearson_r"],
                    stats["r2"],
                    stats["slope"],
                ]
            )
        writer.writerow(
            [
                "global_total_fanout",
                "",
                int(total_fanout["n_samples"]),
                total_fanout["pearson_r"],
                total_fanout["r2"],
                total_fanout["slope"],
            ]
        )


def _update_loss_bins(
    layer_bin_stats: dict[int, dict[int, dict[str, float | int]]],
    layer_idx: int,
    fanout_valid: torch.Tensor,
    loss_valid: torch.Tensor,
) -> None:
    stats = layer_bin_stats[layer_idx]
    _update_loss_bin_stats(stats, fanout_valid, loss_valid)


def _update_loss_bin_stats(
    stats: dict[int, dict[str, float | int]],
    fanout_valid: torch.Tensor,
    loss_valid: torch.Tensor,
) -> None:
    if fanout_valid.numel() == 0:
        return
    fanout_valid = fanout_valid.to(torch.int64)
    loss_valid = loss_valid.to(torch.float64)
    unique_bins = torch.unique(fanout_valid)
    for bin_val in unique_bins.tolist():
        mask = fanout_valid == bin_val
        loss_bin = loss_valid[mask]
        if loss_bin.numel() == 0:
            continue
        stat = stats.setdefault(
            int(bin_val),
            {"count": 0, "sum_loss": 0.0, "sum_sq_loss": 0.0},
        )
        stat["count"] = int(stat["count"]) + int(loss_bin.numel())
        stat["sum_loss"] = float(stat["sum_loss"]) + float(loss_bin.sum().item())
        stat["sum_sq_loss"] = float(stat["sum_sq_loss"]) + float((loss_bin * loss_bin).sum().item())


def collect_selected_layer_expert_logits(
    model,
    val_loader,
    eval_steps: int,
    device: torch.device,
) -> tuple[
    dict[tuple[int, int], torch.Tensor],
    dict,
    dict[int, dict[int, dict[str, float | int]]],
    dict[int, dict[str, float | int]],
    dict[int, torch.Tensor],
    dict[int, torch.Tensor],
    dict[int, dict[str, float | int | None]],
    dict[str, float | int | None],
]:
    n_layer = model.config.n_layer
    target_layers = _selected_layers(n_layer)
    target_layer_set = set(target_layers)

    logits_by_pair: dict[tuple[int, int], list[torch.Tensor]] = {}
    cutoff_ema_by_pair: dict[tuple[int, int], float] = {}
    cutoff_ema_by_layer: dict[int, torch.Tensor] = {}
    analyzed_layers: list[int] = []
    missing_router_layers = set()
    missing_cutoff_layers = set()
    non_moe_layers = set()

    loss_bin_stats: dict[int, dict[int, dict[str, float | int]]] = defaultdict(dict)
    global_total_loss_bin_stats: dict[int, dict[str, float | int]] = {}
    fanout_position_sum: dict[int, torch.Tensor] = {}
    fanout_position_count: dict[int, torch.Tensor] = {}
    corr_by_layer: dict[int, RunningBivariateStats] = {}
    corr_total_fanout = RunningBivariateStats()
    n_routed_experts_by_layer: dict[int, int] = {}

    for layer_idx, block in enumerate(model.blocks):
        router = _get_router(block.mlp)
        cutoff = _get_cutoff_ema(block.mlp)

        if router is None and cutoff is None:
            non_moe_layers.add(layer_idx)
            if layer_idx in target_layer_set:
                missing_cutoff_layers.add(layer_idx)
            continue

        if router is None:
            if layer_idx in target_layer_set:
                missing_router_layers.add(layer_idx)
            continue

        if cutoff is None:
            if layer_idx in target_layer_set:
                missing_cutoff_layers.add(layer_idx)
            continue

        cutoff = cutoff.detach().to(torch.float32).view(-1)
        cutoff_ema_by_layer[layer_idx] = cutoff.to(device=device)
        analyzed_layers.append(layer_idx)
        n_routed_experts_by_layer[layer_idx] = int(cutoff.numel())

        cutoff_cpu = cutoff.cpu()
        n_routed_experts = int(cutoff.numel())
        if layer_idx in target_layer_set:
            for expert_idx in _selected_experts(layer_idx, n_layer, n_routed_experts):
                if 0 <= expert_idx < n_routed_experts:
                    cutoff_ema_by_pair[(layer_idx, expert_idx)] = float(cutoff_cpu[expert_idx].item())

    analyzed_layer_set = set(analyzed_layers)

    autocast_ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
    with torch.no_grad(), autocast_ctx:
        for _ in range(eval_steps):
            input_ids, _ = next(val_loader)
            input_ids = input_ids.to(device)

            _, T = input_ids.shape
            x = model.wte(input_ids)
            x = norm(x)
            cos_sin = model.cos[:, :T], model.sin[:, :T]
            n_tokens = input_ids.numel()
            token_fanout_by_layer: dict[int, torch.Tensor] = {}

            for layer_idx, block in enumerate(model.blocks):
                x = x + block.attn(norm(x), cos_sin)
                mlp_in = norm(x)

                if layer_idx in analyzed_layer_set or layer_idx in target_layer_set:
                    router = _get_router(block.mlp)
                    if router is None and layer_idx in target_layer_set:
                        missing_router_layers.add(layer_idx)
                    elif router is not None:
                        router_logits = router(mlp_in).float()
                        router_logits = router_logits.view(-1, router_logits.shape[-1])

                        if layer_idx in analyzed_layer_set:
                            cutoff = cutoff_ema_by_layer[layer_idx]
                            if cutoff.numel() != router_logits.shape[-1]:
                                raise ValueError(
                                    f"Cutoff/route expert mismatch at layer {layer_idx}: "
                                    f"{cutoff.numel()} vs {router_logits.shape[-1]}"
                                )
                            token_fanout_by_layer[layer_idx] = (
                                router_logits >= cutoff.unsqueeze(0)
                            ).sum(dim=1).to(torch.int64)

                        if layer_idx in target_layer_set:
                            n_routed_experts = router_logits.shape[-1]
                            for expert_idx in _selected_experts(layer_idx, n_layer, n_routed_experts):
                                key = (layer_idx, expert_idx)
                                logits_by_pair.setdefault(key, []).append(
                                    router_logits[:, expert_idx].detach().cpu()
                                )

                if block.mlp_needs_layer_idx:
                    mlp_out, _ = block.mlp(mlp_in, layer_idx=layer_idx)
                else:
                    mlp_out, _ = block.mlp(mlp_in)
                x = x + mlp_out

            x = norm(x)
            logits = model.lm_head(x)
            softcap = 15.0
            logits = softcap * torch.tanh(logits / softcap)

            targets = torch.roll(input_ids, shifts=-1, dims=1)
            losses = F.cross_entropy(
                logits.view(-1, logits.size(-1)),
                targets.view(-1),
                reduction="none",
            ).view(input_ids.shape[0], input_ids.shape[1])

            valid_mask = torch.ones_like(losses, dtype=torch.bool)
            valid_mask[:, -1] = False
            valid_mask_flat = valid_mask.view(-1)
            losses_valid = losses.view(-1)[valid_mask_flat].to(torch.float64).cpu()

            if len(token_fanout_by_layer) == 0:
                continue

            total_fanout_flat = torch.zeros(n_tokens, device=device, dtype=torch.float64)

            for layer_idx, fanout_flat in token_fanout_by_layer.items():
                fanout_bt = fanout_flat.view(input_ids.shape[0], T)
                pos_sum = fanout_bt.to(torch.float64).sum(dim=0).cpu()

                if layer_idx not in fanout_position_sum:
                    fanout_position_sum[layer_idx] = torch.zeros(T, dtype=torch.float64)
                    fanout_position_count[layer_idx] = torch.zeros(T, dtype=torch.int64)

                fanout_position_sum[layer_idx] += pos_sum
                fanout_position_count[layer_idx] += input_ids.shape[0]

                fanout_valid = fanout_flat[valid_mask_flat].cpu()
                _update_loss_bins(
                    layer_bin_stats=loss_bin_stats,
                    layer_idx=layer_idx,
                    fanout_valid=fanout_valid,
                    loss_valid=losses_valid,
                )

                if layer_idx not in corr_by_layer:
                    corr_by_layer[layer_idx] = RunningBivariateStats()
                corr_by_layer[layer_idx].update(
                    fanout_valid.to(torch.float64),
                    losses_valid,
                )
                total_fanout_flat += fanout_flat.to(torch.float64)

            total_fanout_valid = total_fanout_flat[valid_mask_flat].cpu()
            corr_total_fanout.update(total_fanout_valid, losses_valid)
            _update_loss_bin_stats(global_total_loss_bin_stats, total_fanout_valid.to(torch.int64), losses_valid)

    merged = {k: torch.cat(v, dim=0).to(torch.float32) for k, v in logits_by_pair.items() if v}
    corr_by_layer_final = {
        layer_idx: corr_by_layer[layer_idx].finalize()
        for layer_idx in sorted(corr_by_layer)
    }
    corr_total_final = corr_total_fanout.finalize()

    analyzed_layers_sorted = sorted(analyzed_layers)
    if len(analyzed_layers_sorted) == 0:
        raise RuntimeError("No MoE layers with both router and cutoff_ema were found.")

    if len(fanout_position_sum) == 0:
        raise RuntimeError("No fanout-position statistics were collected.")

    if len(loss_bin_stats) == 0:
        raise RuntimeError("No loss-vs-fanout statistics were collected.")

    meta = {
        "target_layers": target_layers,
        "analyzed_layers": analyzed_layers_sorted,
        "highlight_layers": [layer for layer in target_layers if layer in analyzed_layer_set],
        "non_moe_layers": sorted(non_moe_layers),
        "missing_router_layers": sorted(missing_router_layers),
        "missing_cutoff_layers": sorted(missing_cutoff_layers),
        "n_routed_experts_by_layer": {
            f"L{layer_idx}": int(n_routed_experts_by_layer[layer_idx])
            for layer_idx in sorted(n_routed_experts_by_layer)
        },
        "cutoff_ema_by_pair": {
            f"L{layer_idx}_E{expert_idx}": value
            for (layer_idx, expert_idx), value in sorted(cutoff_ema_by_pair.items())
        },
        "position_axis": "absolute_index",
    }
    return (
        merged,
        meta,
        dict(loss_bin_stats),
        global_total_loss_bin_stats,
        fanout_position_sum,
        fanout_position_count,
        corr_by_layer_final,
        corr_total_final,
    )


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig) -> None:
    config_dict = OmegaConf.to_container(cfg, resolve=True)
    config = Config.from_dict(config_dict)
    config.validate()

    checkpoint_path = config.eval.core_checkpoint_path
    if not checkpoint_path:
        raise ValueError("eval.core_checkpoint_path must be set")
    checkpoint_path = str(checkpoint_path)
    if not Path(checkpoint_path).exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    ddp, rank, _local_rank, world_size, device = compute_init(
        seed=config.training.seed,
        expert_parallel=False,
    )
    if ddp:
        raise RuntimeError("Single-GPU only: do not launch with torchrun")

    try:
        model, _tokenizer, checkpoint_cfg = load_checkpoint_model(checkpoint_path, device)

        # Use checkpoint sequence length by default so standalone eval mirrors training-time eval.
        ckpt_seq_len = int(checkpoint_cfg.training.sequence_length)
        if config.training.sequence_length != ckpt_seq_len:
            print0(
                "Overriding eval sequence length from "
                f"{config.training.sequence_length} to checkpoint value {ckpt_seq_len}"
            )
            config.training.sequence_length = ckpt_seq_len

        if model.config.block_size < config.training.sequence_length:
            raise ValueError(
                "Eval sequence length exceeds model block size: "
                f"{config.training.sequence_length} > {model.config.block_size}"
            )

        eval_steps = compute_eval_steps(config, world_size=world_size)
        val_loader = create_data_loader(
            data_path=config.data.data_path,
            batch_size=config.training.per_device_batch_size,
            seq_len=config.training.sequence_length,
            tokenizer_dir=config.data.tokenizer_dir,
            tokenizer_threads=config.data.tokenizer_threads,
            tokenizer_batch_size=config.data.tokenizer_batch_size,
            split="val",
            device=device,
        )

        (
            logits_by_pair,
            collect_meta,
            loss_bin_stats,
            global_total_loss_bin_stats,
            fanout_position_sum,
            fanout_position_count,
            corr_by_layer,
            corr_total_fanout,
        ) = collect_selected_layer_expert_logits(
            model=model,
            val_loader=val_loader,
            eval_steps=eval_steps,
            device=device,
        )

        if not logits_by_pair:
            raise RuntimeError("No router logits were collected for selected layer/expert pairs.")

        output_dir = (
            Path(config.output_dir)
            / config.experiment_name
            / "eval_logs"
            / "routing_logit_hist"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        summary: dict[str, object] = {
            "checkpoint_path": checkpoint_path,
            "eval_steps": eval_steps,
            "batch_size": config.training.per_device_batch_size,
            "sequence_length": config.training.sequence_length,
            "eval_tokens": config.training.eval_tokens,
            "selected_layers": collect_meta["target_layers"],
            "analyzed_layers": collect_meta["analyzed_layers"],
            "non_moe_layers": collect_meta["non_moe_layers"],
            "missing_router_layers": collect_meta["missing_router_layers"],
            "missing_cutoff_layers": collect_meta["missing_cutoff_layers"],
            "position_axis": collect_meta["position_axis"],
            "highlight_layers": collect_meta["highlight_layers"],
            "n_routed_experts_by_layer": collect_meta["n_routed_experts_by_layer"],
            "pairs": {},
        }

        for (layer_idx, expert_idx), values in sorted(logits_by_pair.items()):
            pair_name = f"L{layer_idx}_E{expert_idx}"
            fig_name = f"routing_logits_hist_{pair_name}.png"
            fig_path = output_dir / fig_name
            cutoff_ema = collect_meta["cutoff_ema_by_pair"].get(pair_name)
            _plot_histogram(
                values,
                title=f"Router Logits Histogram ({pair_name})",
                output_path=fig_path,
                cutoff_ema=cutoff_ema,
            )

            pair_stats = _tensor_stats(values)
            pair_stats["figure"] = fig_name
            pair_stats["cutoff_ema"] = cutoff_ema
            summary["pairs"][pair_name] = pair_stats

        loss_vs_fanout_json = _finalize_loss_bin_stats(loss_bin_stats)
        summary["loss_vs_fanout"] = loss_vs_fanout_json

        per_layer_fanout_max = max(
            (int(v) for v in collect_meta["n_routed_experts_by_layer"].values()),
            default=0,
        )
        global_total_fanout_max = sum(
            int(v) for v in collect_meta["n_routed_experts_by_layer"].values()
        )
        summary["fanout_axes"] = {
            "per_layer_max": per_layer_fanout_max,
            "global_total_max": global_total_fanout_max,
        }

        loss_vs_total_fanout_json = _finalize_global_loss_bin_stats(
            global_total_loss_bin_stats,
            min_count_for_plot=GLOBAL_TOTAL_FANOUT_MIN_COUNT,
        )
        summary["loss_vs_total_fanout_global"] = {
            "min_count_for_plot": GLOBAL_TOTAL_FANOUT_MIN_COUNT,
            "bins": loss_vs_total_fanout_json,
        }

        fanout_position_means: dict[int, list[float]] = {}
        for layer_idx in sorted(fanout_position_sum):
            sums = fanout_position_sum[layer_idx]
            counts = fanout_position_count[layer_idx].to(torch.float64).clamp_min(1.0)
            fanout_position_means[layer_idx] = (sums / counts).tolist()

        layer_values = [fanout_position_means[layer_idx] for layer_idx in sorted(fanout_position_means)]
        if len(layer_values) == 0:
            raise RuntimeError("No fanout-vs-position means were computed.")
        global_mean = [
            float(sum(layer_vals[pos] for layer_vals in layer_values) / len(layer_values))
            for pos in range(len(layer_values[0]))
        ]

        summary["fanout_vs_position"] = {
            f"L{layer_idx}": {
                "mean_fanout_by_position": values
            }
            for layer_idx, values in sorted(fanout_position_means.items())
        }
        summary["fanout_vs_position"]["global_mean_across_layers"] = global_mean

        summary["loss_fanout_correlation"] = {
            "per_layer": {
                f"L{layer_idx}": stats for layer_idx, stats in sorted(corr_by_layer.items())
            },
            "global_total_fanout": corr_total_fanout,
        }

        _plot_loss_vs_fanout(
            layer_bin_stats=loss_bin_stats,
            highlight_layers=collect_meta["highlight_layers"],
            per_layer_fanout_max=per_layer_fanout_max,
            output_path=output_dir / "loss_vs_fanout_by_layer.png",
        )
        _plot_loss_vs_total_fanout(
            global_bin_stats=global_total_loss_bin_stats,
            output_path=output_dir / "loss_vs_total_fanout_global.png",
            min_count_for_plot=GLOBAL_TOTAL_FANOUT_MIN_COUNT,
            global_fanout_max=global_total_fanout_max,
        )
        _plot_fanout_vs_position(
            fanout_position_means=fanout_position_means,
            global_mean=global_mean,
            output_path=output_dir / "fanout_vs_position.png",
        )

        _write_loss_vs_fanout_csv(
            layer_bin_stats=loss_bin_stats,
            output_path=output_dir / "loss_vs_fanout_by_layer.csv",
        )
        with open(output_dir / "loss_vs_fanout_by_layer.json", "w", encoding="utf-8") as f:
            json.dump(loss_vs_fanout_json, f, indent=2)
        _write_loss_vs_total_fanout_csv(
            global_bin_stats=global_total_loss_bin_stats,
            output_path=output_dir / "loss_vs_total_fanout_global.csv",
            min_count_for_plot=GLOBAL_TOTAL_FANOUT_MIN_COUNT,
        )
        with open(output_dir / "loss_vs_total_fanout_global.json", "w", encoding="utf-8") as f:
            json.dump(summary["loss_vs_total_fanout_global"], f, indent=2)

        _write_fanout_vs_position_csv(
            fanout_position_sum=fanout_position_sum,
            fanout_position_count=fanout_position_count,
            output_path=output_dir / "fanout_vs_position_by_layer.csv",
        )
        _write_fanout_vs_position_global_csv(
            global_mean=global_mean,
            output_path=output_dir / "fanout_vs_position_global.csv",
        )

        _write_correlation_csv(
            per_layer=corr_by_layer,
            total_fanout=corr_total_fanout,
            output_path=output_dir / "loss_fanout_correlation.csv",
        )
        with open(output_dir / "loss_fanout_correlation.json", "w", encoding="utf-8") as f:
            json.dump(summary["loss_fanout_correlation"], f, indent=2)

        summary_path = output_dir / "routing_logits_hist_stats.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        print0(f"Saved routing histogram outputs to {output_dir}")
        print0(f"Saved loss-vs-fanout outputs to {output_dir}")
        print0(f"Saved fanout-vs-position outputs to {output_dir}")
        print0(f"Saved correlation outputs to {output_dir}")
        print0(f"Saved stats JSON to {summary_path}")
    finally:
        compute_cleanup()


if __name__ == "__main__":
    main()
