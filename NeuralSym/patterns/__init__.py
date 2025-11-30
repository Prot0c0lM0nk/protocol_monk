"""
Pattern analysis module for statistical self-improvement
Blueprint 4: Statistical Self-Improvement (Patterns)

This module learns from tool interaction history to predict success probabilities,
recommend optimal approaches, and warn about potential failures.
"""

from .analyzer import AdvancedPatternAnalyzer
from .base import (
    ComplexityLevel,
    ContextSnapshot,
    Interaction,
    Outcome,
    PredictiveRecommendation,
    ToolProfile,
    calculate_confidence_interval,
)

__all__ = [
    "Outcome",
    "ComplexityLevel",
    "ContextSnapshot",
    "Interaction",
    "ToolProfile",
    "PredictiveRecommendation",
    "calculate_confidence_interval",
    "AdvancedPatternAnalyzer",
]
