"""Metrics tracking for training."""

from typing import Dict, List, Any, Optional
from collections import defaultdict
import numpy as np


class MetricsTracker:
    """Track and aggregate training metrics."""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.step_metrics = {}
    
    def update(self, metrics: Dict[str, float]) -> None:
        """Update metrics for current step."""
        self.step_metrics = metrics.copy()
        for key, value in metrics.items():
            self.metrics[key].append(value)
    
    def get_current(self) -> Dict[str, float]:
        """Get current step metrics."""
        return self.step_metrics.copy()
    
    def get_average(self, key: str, last_n: Optional[int] = None) -> float:
        """Get average of a metric over last n steps."""
        if key not in self.metrics:
            return 0.0
        
        values = self.metrics[key]
        if last_n is not None:
            values = values[-last_n:]
        
        return float(np.mean(values)) if values else 0.0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics for all metrics."""
        summary = {}
        
        for key, values in self.metrics.items():
            if not values:
                continue
            
            summary[key] = {
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'last': float(values[-1]),
                'count': len(values)
            }
        
        return summary
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.metrics.clear()
        self.step_metrics.clear()
    
    def load_state(self, state: Dict[str, List[float]]) -> None:
        """Load metrics state."""
        # Validate that state contains lists of numeric values
        validated_state = {}
        for key, values in state.items():
            if isinstance(values, list) and all(isinstance(v, (int, float)) for v in values):
                validated_state[key] = values
            # Skip invalid entries (e.g., from old checkpoint format)
        self.metrics = defaultdict(list, validated_state)
    
    def save_state(self) -> Dict[str, List[float]]:
        """Save metrics state."""
        return dict(self.metrics) 