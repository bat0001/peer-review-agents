"""Organize flat metrics into hierarchical wandb structure."""

from typing import Dict


class MetricsOrganizer:
    """Convert flat model metrics to hierarchical wandb paths.

    All models (ET, EC, ET_shared) use identical metric names (no prefixes).
    Model identification is handled via wandb run config/name.

    Hierarchical structure:
        train/loss, train/lr, train/grad_norm
        eval/loss
        routing/coverage/, routing/cutoffs/, routing/weights/, routing/logits/
        routing/layers/L{i}/
        system/throughput, system/step_time
        chars/
    """

    def __init__(self):
        """Initialize metrics organizer (no model_type needed)."""
        pass

    def organize(self, flat_metrics: Dict[str, float]) -> Dict[str, float]:
        """Convert flat metrics to hierarchical structure.

        Args:
            flat_metrics: Flat metric dict from model/trainer

        Returns:
            Hierarchical metric dict for wandb logging
        """
        hierarchical = {}

        for key, value in flat_metrics.items():
            new_key = self._map_metric(key)
            hierarchical[new_key] = value

        return hierarchical

    def _map_metric(self, key: str) -> str:
        """Map flat metric key to hierarchical path.

        Args:
            key: Flat metric key

        Returns:
            Hierarchical path for wandb
        """
        # Handle eval prefix first
        eval_prefix = ""
        if key.startswith("eval/"):
            eval_prefix = "eval/"
            key = key.removeprefix("eval/")

        # Training metrics
        if key == "loss":
            if not eval_prefix:
                return "train/loss"
            else:
                return "eval/loss"
        if key == "learning_rate":
            return "train/lr"
        if key == "grad_norm":
            return "train/grad_norm"
        if key == "train_loss_ema":
            return "train/loss_ema"

        # System metrics
        if key in ["throughput", "step_time", "gpu_util", "memory"]:
            return f"system/{key}"

        # Router coverage metrics
        if key in ["avg_experts_per_token", "max_experts_per_token",
                   "tokens_with_no_expert", "tokens_with_1_expert",
                   "tokens_with_2+_experts"]:
            return f"{eval_prefix}routing/coverage/{key}"

        # Cutoffs
        if key == "cutoffs":
            return f"{eval_prefix}routing/cutoffs/current"
        if key == "cutoff_ema":
            return f"{eval_prefix}routing/cutoffs/ema"
        if key == "cutoff_abs_deviation":
            return f"{eval_prefix}routing/cutoffs/temporal/abs_deviation"

        # Activation weights
        if key.startswith("activation_weight_"):
            stat = key.removeprefix("activation_weight_")
            return f"{eval_prefix}routing/weights/{stat}"

        # Router logits
        if key.startswith("router_logit_"):
            stat = key.removeprefix("router_logit_")
            return f"{eval_prefix}routing/logits/{stat}"

        # Capacity metrics (threshold mode only)
        if key.startswith("capacity_"):
            # e.g., "capacity_overflow_rate" -> "routing/capacity/overflow_rate"
            metric = key.removeprefix("capacity_")
            return f"{eval_prefix}routing/capacity/{metric}"

        # Normalization metrics (threshold mode and other modes with normalizer)
        if key.startswith("norm_") or key in ["select_norm_sum", "all_norm_sum", "zero_weight_ratio"]:
            # Group under routing/normalization/
            if key.startswith("norm_"):
                metric = key.removeprefix("norm_")
            else:
                metric = key
            return f"{eval_prefix}routing/normalization/{metric}"

        # Representative layers
        if key.startswith("repr_L"):
            # e.g., "repr_L0_E0_cutoff" -> "routing/layers/L0/E0_cutoff"
            # Also handles "repr_L0_E0_raw_usage" -> "routing/layers/L0/E0_raw_usage"
            parts = key.split("_", 2)  # ["repr", "L0", "E0_cutoff"]
            if len(parts) == 3:
                layer = parts[1]
                metric = parts[2]
                return f"{eval_prefix}routing/layers/{layer}/{metric}"

        # Expert usage (vector metric)
        if key == "expert_usage":
            return f"{eval_prefix}routing/expert_usage"

        # Character-level metrics (if prefixed with "chars/")
        if key.startswith("chars/"):
            return key  # Keep as-is

        # Fallback: keep at root
        return key
