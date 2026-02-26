"""GEC (Global Expert Choice) model implementations."""

from .gec import GECMLP
from .gec_trainable_threshold import GECMLPTrainableThreshold
from .reference import GECMLPReference
from .segmented import GECSegmentedMLP
from .triton import GECTritonMLP
from .triton1 import GECTritonMLP as GECTritonMLP1

__all__ = [
    "GECMLP",
    "GECMLPTrainableThreshold",
    "GECMLPReference",
    "GECSegmentedMLP",
    "GECTritonMLP",
    "GECTritonMLP1",
]
