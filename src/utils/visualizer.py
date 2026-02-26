"""Evaluation visualization for GEC routing analysis."""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Any

import torch
import torch.nn.functional as F
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server environments


class EvalVisualizer:
    """Collect and visualize routing behavior during evaluation.

    Design:
    - Self-contained: All data extraction and processing happens here
    - Minimal overhead: Only processes representative layers
    - Two-level output:
      1. JSON logging (every eval_interval): Lightweight statistics
      2. Plot generation (every plot_interval): Full visualizations
    """

    def __init__(self, config, output_dir: Path, num_layers: int):
        """
        Initialize visualizer.

        Args:
            config: Training configuration
            output_dir: Output directory for logs and plots
            num_layers: Total number of layers in model
        """
        self.config = config
        self.output_dir = Path(output_dir)
        self.num_layers = num_layers

        # Representative layers (every 4 layers + last)
        self.repr_layers = {i for i in range(0, num_layers, 4)}
        self.repr_layers.add(num_layers - 1)

        # Create output directories
        self.eval_logs_dir = self.output_dir / "eval_logs"
        self.viz_dir = self.output_dir / "visualizations"
        self.eval_logs_dir.mkdir(parents=True, exist_ok=True)
        self.viz_dir.mkdir(parents=True, exist_ok=True)

        # Accumulated data storage (cleared at start of each eval)
        self.accumulated_data: Dict[int, Dict[str, List[torch.Tensor]]] = {}

        # JSON log files
        self.expert_counts_file = self.eval_logs_dir / "expert_counts.json"
        self.weight_percentiles_file = self.eval_logs_dir / "weight_percentiles.json"

        # Initialize JSON files if they don't exist
        for json_file in [self.expert_counts_file, self.weight_percentiles_file]:
            if not json_file.exists():
                with open(json_file, 'w') as f:
                    json.dump([], f)

    def clear_accumulated_data(self):
        """Reset accumulators at start of each eval pass."""
        self.accumulated_data = {}

    def accumulate_batch(self, model_output, labels: torch.Tensor, layer_data: Optional[Dict] = None):
        """
        Accumulate batch statistics during eval iteration.

        Args:
            model_output: ModelOutput from forward pass
            labels: Target labels (B, T)
            layer_data: Optional dict containing per-layer routing data
                       Format: {layer_idx: {'weights': ..., 'fanout': ..., 'cutoffs': ...}}
        """
        # Compute per-token loss and entropy from logits
        per_token_loss = self._compute_per_token_loss(model_output.logits, labels)
        per_token_entropy = self._compute_entropy(model_output.logits)

        # If layer_data is provided (from model), accumulate it
        if layer_data is not None:
            for layer_idx, data in layer_data.items():
                if layer_idx in self.repr_layers:
                    if layer_idx not in self.accumulated_data:
                        self.accumulated_data[layer_idx] = defaultdict(list)

                    # Accumulate routing data
                    if 'weights' in data:
                        self.accumulated_data[layer_idx]['weights'].append(data['weights'].cpu())
                    if 'fanout' in data:
                        self.accumulated_data[layer_idx]['fanout'].append(data['fanout'].cpu())
                    if 'cutoffs' in data:
                        self.accumulated_data[layer_idx]['cutoffs'].append(data['cutoffs'].cpu())
                    if 'router_logits' in data:
                        self.accumulated_data[layer_idx]['router_logits'].append(data['router_logits'].cpu())

                    # Accumulate per-token metrics (match batch size to fanout)
                    if 'fanout' in data:
                        n_tokens = data['fanout'].shape[0]
                        self.accumulated_data[layer_idx]['loss'].append(per_token_loss[:n_tokens].cpu())
                        self.accumulated_data[layer_idx]['entropy'].append(per_token_entropy[:n_tokens].cpu())

    def _compute_per_token_loss(self, logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Compute per-token cross-entropy loss.

        Args:
            logits: Model logits (B, T, vocab_size)
            labels: Target labels (B, T)

        Returns:
            Per-token loss (B*T,)
        """
        return F.cross_entropy(
            logits.view(-1, logits.size(-1)),
            labels.view(-1),
            reduction='none'
        )

    def _compute_entropy(self, logits: torch.Tensor) -> torch.Tensor:
        """
        Compute prediction entropy from output logits.

        Args:
            logits: Model logits (B, T, vocab_size)

        Returns:
            Per-token entropy (B*T,)
        """
        probs = F.softmax(logits.view(-1, logits.size(-1)), dim=-1)
        entropy = -(probs * torch.log(probs + 1e-10)).sum(dim=-1)
        return entropy

    def log_eval_stats(self, step: int):
        """
        Compute and log lightweight JSON statistics.

        Called after every eval pass (every eval_interval).

        Args:
            step: Current training step
        """
        if not self.accumulated_data:
            return

        # Prepare data structures
        expert_counts_entry = {"step": step}
        weight_percentiles_entry = {"step": step}

        for layer_idx in self.repr_layers:
            if layer_idx not in self.accumulated_data:
                continue

            data = self.accumulated_data[layer_idx]

            # Skip if no data
            if not data.get('fanout') or not data.get('weights'):
                continue

            # Concatenate accumulated batches
            all_fanout = torch.cat(data['fanout'])
            all_weights = torch.cat(data['weights'])

            # 1. Expert activation histogram
            max_experts = int(all_fanout.max().item()) + 1
            counts = {}
            for n in range(max_experts):
                if n < 4:
                    count = (all_fanout == n).sum().item()
                    percent = 100.0 * count / len(all_fanout)
                    counts[f"{n}_experts"] = {"count": count, "percent": round(percent, 2)}
                else:
                    # Aggregate 4+ experts
                    if "4+_experts" not in counts:
                        count = (all_fanout >= 4).sum().item()
                        percent = 100.0 * count / len(all_fanout)
                        counts["4+_experts"] = {"count": count, "percent": round(percent, 2)}

            expert_counts_entry[f"layer_{layer_idx}"] = counts

            # 2. Router weight percentiles
            percentiles_values = torch.quantile(
                all_weights.float(),
                torch.tensor([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
            )
            percentiles = {
                f"p{int(p*100)}": round(v.item(), 4)
                for p, v in zip([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99], percentiles_values)
            }
            weight_percentiles_entry[f"layer_{layer_idx}"] = percentiles

        # Append to JSON files
        self._append_to_json(self.expert_counts_file, expert_counts_entry)
        self._append_to_json(self.weight_percentiles_file, weight_percentiles_entry)

    def _append_to_json(self, filepath: Path, entry: Dict):
        """Append entry to JSON array file."""
        # Read existing data
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Append new entry
        data.append(entry)

        # Write back
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def create_plots(self, step: int):
        """
        Generate visualizations from accumulated data.

        Called when step % plot_interval == 0.

        Args:
            step: Current training step
        """
        if not self.accumulated_data:
            return

        # Create step-specific directory
        step_dir = self.viz_dir / f"step_{step}"
        step_dir.mkdir(exist_ok=True)

        for layer_idx in self.repr_layers:
            if layer_idx not in self.accumulated_data:
                continue

            data = self.accumulated_data[layer_idx]

            # Skip if insufficient data
            if not all(k in data for k in ['weights', 'fanout', 'loss']):
                continue

            # Concatenate all batches
            all_weights = torch.cat(data['weights'])
            all_fanout = torch.cat(data['fanout'])
            all_loss = torch.cat(data['loss'])
            all_entropy = torch.cat(data['entropy']) if 'entropy' in data else None

            # Generate plots
            self._plot_weight_cdf(all_weights, step_dir, layer_idx)
            self._plot_loss_violin(all_fanout, all_loss, step_dir, layer_idx)

            if all_entropy is not None:
                self._plot_entropy_violin(all_entropy, all_fanout, step_dir, layer_idx)

    def _plot_weight_cdf(self, weights: torch.Tensor, output_dir: Path, layer_idx: int):
        """Plot cumulative distribution of router weights."""
        plt.figure(figsize=(8, 6))

        # Sort weights for CDF
        sorted_weights = torch.sort(weights.flatten())[0].numpy()
        cdf = torch.arange(1, len(sorted_weights) + 1).float() / len(sorted_weights)

        plt.plot(sorted_weights, cdf.numpy())
        plt.xlabel('Router Weight')
        plt.ylabel('Cumulative Probability')
        plt.title(f'Router Weight CDF - Layer {layer_idx}')
        plt.grid(True, alpha=0.3)

        # Save
        save_dir = output_dir / "weight_cdf"
        save_dir.mkdir(exist_ok=True)
        plt.savefig(save_dir / f"layer_{layer_idx}.png", dpi=150, bbox_inches='tight')
        plt.close()

    def _plot_loss_violin(self, fanout: torch.Tensor, loss: torch.Tensor, output_dir: Path, layer_idx: int):
        """Plot violin plot of loss distribution by expert count."""
        plt.figure(figsize=(10, 6))

        # Group losses by fanout (always show 0, 1, 2, 3, 4+)
        loss_by_fanout = []
        labels = []
        positions = []

        for n in range(5):
            if n < 4:
                mask = fanout == n
                labels.append(str(n))
            else:
                mask = fanout >= 4
                labels.append("4+")

            if mask.sum() > 0:
                loss_by_fanout.append(loss[mask].numpy())
                positions.append(n)
            # Note: Skip empty categories (no data to plot)

        # Create violin plot
        if loss_by_fanout:
            parts = plt.violinplot(loss_by_fanout, positions=positions, showmeans=True)
        plt.xticks(range(5), ["0", "1", "2", "3", "4+"])
        plt.xlabel('Number of Experts')
        plt.ylabel('Token Loss')
        plt.title(f'Loss Distribution by Expert Count - Layer {layer_idx}')
        plt.grid(True, alpha=0.3, axis='y')

        # Save
        save_dir = output_dir / "loss_by_experts"
        save_dir.mkdir(exist_ok=True)
        plt.savefig(save_dir / f"layer_{layer_idx}_violin.png", dpi=150, bbox_inches='tight')
        plt.close()

    def _plot_entropy_violin(self, entropy: torch.Tensor, fanout: torch.Tensor,
                             output_dir: Path, layer_idx: int):
        """Plot violin of entropy distribution by expert count."""
        plt.figure(figsize=(10, 6))

        # Group entropy by expert count (always show 0, 1, 2, 3, 4+)
        entropy_by_fanout = []
        positions = []

        for n in range(5):
            if n < 4:
                mask = fanout == n
            else:
                mask = fanout >= 4

            if mask.sum() > 0:
                entropy_by_fanout.append(entropy[mask].numpy())
                positions.append(n)
            # Note: Skip empty categories (no data to plot)

        # Create violin plot
        if entropy_by_fanout:
            plt.violinplot(entropy_by_fanout, positions=positions, showmeans=True)
        plt.xticks(range(5), ["0", "1", "2", "3", "4+"])
        plt.xlabel('Number of Experts')
        plt.ylabel('Token Entropy')
        plt.title(f'Entropy Distribution by Expert Count - Layer {layer_idx}')
        plt.grid(True, alpha=0.3, axis='y')

        # Save
        save_dir = output_dir / "entropy_vs_experts"
        save_dir.mkdir(exist_ok=True)
        plt.savefig(save_dir / f"layer_{layer_idx}_violin.png", dpi=150, bbox_inches='tight')
        plt.close()
