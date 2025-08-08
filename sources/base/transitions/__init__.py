"""Transition detection algorithms for signal processing."""

from .categorical import BaseCategoricalTransitionDetector, Transition
from .pelt import BasePELTTransitionDetector

__all__ = [
    'BaseCategoricalTransitionDetector',
    'BasePELTTransitionDetector',
    'Transition'
]