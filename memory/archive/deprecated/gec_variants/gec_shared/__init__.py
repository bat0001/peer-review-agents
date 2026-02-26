"""GEC with Shared Expert implementations.

All implementations now use 2D ParameterList for expert weights (enables per-expert
optimizer states like DistMuon) while maintaining efficient batched computation.

Base Implementation:
    GECSharedMLP: Base class with 2D parameters (from shared.py)

Variants:
    GECSharedMLPTrainableThreshold: Trainable threshold routing
    GECSharedMLPCapacityThreshold: Capacity-aware trainable threshold routing
    AddIntoSharedGECMLP: Optimized add-into-shared implementation
    AddIntoSharedExplicitGECMLP: Explicit dtype casting variant (for benchmarking)
    GECSharedMLPCSR: CSR-based token-parallel scatter variant
"""

from .shared import GECSharedMLP
from .shared_trainable_threshold import GECSharedMLPTrainableThreshold
from .shared_capacity_batched import GECSharedMLPCapacityBatched
from .shared_capacity_threshold import GECSharedMLPCapacityThreshold  # FOR-LOOP VERSION (for testing)
from .add_into_shared import AddIntoSharedGECMLP
from .add_into_shared_explicit import AddIntoSharedExplicitGECMLP
from .csr_routing import GECSharedMLPCSR

# TEMPORARILY using FOR-LOOP version to test OOM fix
GECSharedMLPCapacityThreshold = GECSharedMLPCapacityBatched  # (batched version)

__all__ = [
    "GECSharedMLP",
    "GECSharedMLPTrainableThreshold",
    "GECSharedMLPCapacityThreshold",
    "GECSharedMLPCapacityBatched",
    "AddIntoSharedGECMLP",
    "AddIntoSharedExplicitGECMLP",
    "GECSharedMLPCSR"
]
