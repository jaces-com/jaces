"""
Signal Analysis Module

This module is responsible for analyzing signals to detect temporal boundaries 
(for episodic signals) and state transitions (for ambient signals).
It processes normalized signals to identify when events start/end and when 
states change, preparing the data for event synthesis.
"""

from .analyzer import SignalAnalyzer

__all__ = ['SignalAnalyzer']