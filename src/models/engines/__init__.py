"""Expert computation engine for GEC.

Provides ExpertEngine which handles routed expert computation
and returns pre-scatter outputs (h_flat, indices, metrics).
"""

from .engine import ExpertEngine
from .ep_checkpoint import (
    compute_local_experts,
    extract_local_expert_state,
    merge_expert_states,
    shard_state_for_rank,
)

__all__ = [
    'ExpertEngine',
    'compute_local_experts',
    'extract_local_expert_state',
    'merge_expert_states',
    'shard_state_for_rank',
]
