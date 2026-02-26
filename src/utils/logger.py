"""Logging utilities for training."""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import json

import torch

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False


class Logger:
    """Logger for training metrics and messages."""

    def __init__(self, config: Any, output_dir: Path, rank: int = 0):
        """
        Initialize logger.

        Args:
            config: Logging configuration
            output_dir: Directory for log files
            rank: Process rank (only rank 0 logs)
        """
        self.config = config
        self.output_dir = output_dir
        self.rank = rank
        self.should_log = rank == 0

        if not self.should_log:
            return

        # Create log file
        self.log_file = output_dir / "training.log"

        # Initialize wandb if requested
        self.use_wandb = config.use_wandb and WANDB_AVAILABLE
        if self.use_wandb:
            self._init_wandb()

        # Initialize metrics organizer for hierarchical wandb logging
        from .metrics_organizer import MetricsOrganizer
        self.metrics_organizer = MetricsOrganizer()
    
    def _init_wandb(self) -> None:
        """Initialize Weights & Biases."""
        wandb.init(
            project=self.config.wandb_project,
            entity=self.config.wandb_entity,
            name=self.output_dir.name,
            config=self.config.__dict__ if hasattr(self.config, '__dict__') else dict(self.config),
            dir=str(self.output_dir)
        )
    
    def log(self, message: str) -> None:
        """Log a message."""
        if not self.should_log:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Console
        print(formatted_message)
        
        # File
        with open(self.log_file, 'a') as f:
            f.write(formatted_message + '\n')
    
    def log_metrics(
        self,
        step: int,
        metrics: Dict[str, float],
        prefix: str = ""
    ) -> None:
        """Log metrics.

        Args:
            step: Training step number
            metrics: Metrics dictionary
            prefix: Optional prefix for metric keys
        """
        if not self.should_log:
            return

        # Assert: No tensors allowed (defense in depth)
        for key, value in metrics.items():
            assert not torch.is_tensor(value), \
                f"Tensor metric '{key}' passed to logger! " \
                f"Passing tensor-type metrics risks deadlocks. " \
                f"ModelBase.forward() should have converted all metrics to Python types. " \
                f"If you see this, there's a bug in the metric pipeline."

            # Validate expected types
            assert isinstance(value, (int, float, list, bool)), \
                f"Unexpected metric type for '{key}': {type(value)}. " \
                f"Expected int, float, list, or bool."

        # Format metrics (flat for console/file)
        flat_metrics = {}
        for key, value in metrics.items():
            formatted_key = f"{prefix}{key}"
            flat_metrics[formatted_key] = value

        # Console log (flat, skip vectors for readability)
        scalar_metrics = {k: v for k, v in flat_metrics.items() if isinstance(v, (int, float))}
        metrics_str = ", ".join(f"{k}: {v:.4f}" for k, v in scalar_metrics.items())
        self.log(f"Step {step}: {metrics_str}")

        # Wandb log (hierarchical)
        if self.use_wandb:
            hierarchical_metrics = self.metrics_organizer.organize(flat_metrics)
            wandb.log(hierarchical_metrics, step=step)

        # JSON log (flat for backward compatibility)
        json_log = {
            'step': step,
            'metrics': flat_metrics,
            'timestamp': datetime.now().isoformat()
        }

        json_file = self.output_dir / "metrics.jsonl"
        with open(json_file, 'a') as f:
            f.write(json.dumps(json_log) + '\n')
    
    def log_config(self, config: Dict[str, Any]) -> None:
        """Log configuration."""
        if not self.should_log:
            return
        
        config_file = self.output_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        self.log("Configuration saved to config.json")
    
    def finish(self) -> None:
        """Finish logging."""
        if self.should_log and self.use_wandb:
            wandb.finish() 