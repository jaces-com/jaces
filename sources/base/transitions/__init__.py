"""Transition detection algorithms for signal processing."""

from .categorical import BaseCategoricalTransitionDetector, Transition

# Note: Import BasePELTTransitionDetector only when needed to avoid numpy dependency
# from .pelt import BasePELTTransitionDetector

__all__ = [
    'BaseCategoricalTransitionDetector',
    'Transition'
]