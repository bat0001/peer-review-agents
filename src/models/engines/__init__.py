"""Expert computation engine for GEC.

Provides ExpertEngine which handles routed expert computation
and returns pre-scatter outputs (h_flat, indices, metrics).
"""

from .engine import ExpertEngine

__all__ = ['ExpertEngine']
