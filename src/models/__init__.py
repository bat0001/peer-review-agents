"""Model implementations for GPT2 training framework."""

from .model_base import BaseGPT, ModelConfig, ModelOutput
from .gec import GECMLP
from .gec_shared import GECSharedMLP
# EC/EC_shared use legacy RouterMixin pattern - import separately if needed
# from .ec import ECMLP
# from .ec_shared import ECSharedMLP

__all__ = [
    "BaseGPT",
    "ModelConfig",
    "ModelOutput",
    "GECMLP",
    "GECSharedMLP",
]
